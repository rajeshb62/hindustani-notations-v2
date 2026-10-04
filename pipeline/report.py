#!/usr/bin/env python3
"""Where is each transcription weakest? Measured, so listening can be targeted.

    python3 -m pipeline.report              # every performance
    python3 -m pipeline.report <slug> ...

Per performance (written to data/<slug>/report.json and summarised):
- coverage: share of the time the voice stem is sounding (vad_filter gate)
  that is covered by notes, and the longest uncovered stretches (gaps);
- out-of-raga held notes (when the raga is known), with times;
- listener feedback as checks: "no voice" stretches should have almost no
  notes, "continuous singing" stretches should be covered, "Sa'' not in the
  voice" stretches should have no notes two octaves up, "instrument" stretches
  should have almost no notes;
- sung-sargam agreement where sargam_labels.json exists.

Needs the local voice stem (work/vocals.wav) for coverage; skipped without it.
"""

from __future__ import annotations

import json
import math
import re
import statistics as st
import sys
from pathlib import Path

import numpy as np

from .raga import RAGAS
from .run import DATA
from .transcribe import load_frames, prepare_frames

HOP = 0.01
MIN_GAP_S = 0.5


def _note_mask(notes: list[dict], n: int) -> np.ndarray:
    on = np.zeros(n, bool)
    for x in notes:
        on[int(x["t"] / HOP): int((x["t"] + x["dur"]) / HOP) + 1] = True
    return on


def _runs(mask: np.ndarray, min_len: int) -> list[tuple[float, float]]:
    out, start = [], None
    for i, v in enumerate(np.append(mask, False)):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_len:
                out.append((round(start * HOP, 2), round(i * HOP, 2)))
            start = None
    return out


def coverage(perf: dict, vocals: Path) -> dict | None:
    if not vocals.exists():
        return None
    from .vad_filter import voice_activity

    active, _ = voice_activity(vocals)
    on = _note_mask(perf["notes"], len(active))
    gaps = _runs(active & ~on, int(MIN_GAP_S / HOP))
    gaps.sort(key=lambda g: g[0] - g[1])
    return {
        "voice_seconds": round(active.sum() * HOP, 1),
        "covered": round(float((active & on).sum() / max(1, active.sum())), 3),
        "notes_outside_voice_seconds": round(float((on & ~active).sum() * HOP), 1),
        "gaps_total_seconds": round(sum(b - a for a, b in gaps), 1),
        "longest_gaps": [{"start": a, "end": b} for a, b in gaps[:15]],
    }


def out_of_raga(perf: dict, min_dur: float = 0.3) -> list[dict] | None:
    raga = perf.get("raga")
    if not raga:
        return None
    allowed = RAGAS[raga]
    return [{"t": n["t"], "dur": n["dur"], "label": n["label"]}
            for n in perf["notes"] if n["dur"] >= min_dur and n["swara"] not in allowed]


def _covered(notes: list[dict], a: float, b: float) -> float:
    return sum(max(0.0, min(n["t"] + n["dur"], b) - max(n["t"], a)) for n in notes)


def feedback_checks(perf: dict, feedback: list[dict]) -> list[dict]:
    """Turn free-text listener feedback into pass/fail checks where it says what to expect."""
    out = []
    for f in feedback:
        a, b, text = f["start"], f["end"], f["text"].lower()
        cov = _covered(perf["notes"], a, b) / max(1e-9, b - a)
        if "**" in text or re.search(r"not (in|belong)[^.]*voice", text):
            high = [n["label"] for n in perf["notes"] if a - 2 <= n["t"] < b and n["octave"] >= 2]
            kind, ok, got = "no notes two octaves up", not high, f"{len(high)} such notes"
        elif re.search(r"no vocal|no singer|no singing|no artist voice|background only|instruments? only", text):
            kind, ok, got = "no voice → few notes", cov <= 0.15, f"{100 * cov:.0f}% covered"
        elif re.search(r"continuous|no breath|singing (is )?ongoing|singing here", text):
            kind, ok, got = "singing → covered", cov >= 0.8, f"{100 * cov:.0f}% covered"
        elif re.search(r"instrument|sarangi|harmonium|bleed", text):
            kind, ok, got = "instrument → few notes", cov <= 0.15, f"{100 * cov:.0f}% covered"
        else:
            kind, ok, got = "unclassified", None, f"{100 * cov:.0f}% covered"
        out.append({"start": a, "end": b, "check": kind, "pass": ok, "measured": got, "text": f["text"]})
    return out


# ---- sung sargam: align the listener's syllables to held pitches --------------------
FAM = {"sa": (-60, 60), "re": (60, 260), "ga": (260, 460), "ma": (460, 650),
       "pa": (650, 760), "da": (760, 940), "ni": (940, 1140)}
FAM_OF_SWARA = {"S": "sa", "r": "re", "R": "re", "g": "ga", "G": "ga", "M": "ma", "M+": "ma",
                "P": "pa", "d": "da", "D": "da", "n": "ni", "N": "ni"}
FAM_CENTRE = {"sa": 0, "re": 200, "ga": 360, "ma": 500, "pa": 700, "da": 850, "ni": 1000}


def _tok_cost(tok: str, cents: float) -> float:
    m = ((cents + 60) % 1200) - 60
    best = 9.0
    for alt in tok.rstrip("?").replace("'", "").split("|"):
        a, b = FAM[alt]
        best = min(best, (0 if a <= m < b else min(abs(m - a), abs(m - b))) / 40)
    return best


def _held_pitches(frames, sa_hz: float) -> list[tuple[float, float, float]]:
    segs, cur = [], []

    def flush():
        if len(cur) >= 10:
            segs.append((cur[0][0], cur[-1][0] + HOP, st.median(c for _, c in cur)))
    for f in frames:
        c = 1200 * math.log2(f.hz / sa_hz)
        if cur and (f.t - cur[-1][0] > 0.03 or abs(c - st.median(x for _, x in cur[-8:])) > 35):
            flush()
            cur = []
        cur.append((f.t, c))
    flush()
    return segs


def sargam_check(perf: dict, frames_csv: Path, labels: list[dict]) -> list[dict]:
    out = []
    for lab in labels:
        toks = lab["tokens"].split()
        raw = [f for f in load_frames(frames_csv) if lab["start"] <= f.t < lab["end"]]
        segs = _held_pitches(prepare_frames(raw, perf["sa_hz"]), perf["sa_hz"])
        n, m, inf = len(toks), len(segs), 1e9
        D = [[inf] * (m + 1) for _ in range(n + 1)]
        P = {}
        D[0][0] = 0.0
        for i in range(n + 1):
            for j in range(m + 1):
                if D[i][j] >= inf:
                    continue
                if j < m:  # held pitch the listener did not name (ornament)
                    v = D[i][j] + 0.25 + 0.8 * (segs[j][1] - segs[j][0])
                    if v < D[i][j + 1]:
                        D[i][j + 1], P[(i, j + 1)] = v, (i, j, False)
                if i < n and D[i][j] + 1.2 < D[i + 1][j]:  # syllable without a held pitch
                    D[i + 1][j], P[(i + 1, j)] = D[i][j] + 1.2, (i, j, False)
                if i < n and j < m:
                    v = D[i][j] + _tok_cost(toks[i], segs[j][2])
                    if v < D[i + 1][j + 1]:
                        D[i + 1][j + 1], P[(i + 1, j + 1)] = v, (i, j, True)
        i, j, pairs = n, m, []
        while (i, j) != (0, 0):
            pi, pj, matched = P[(i, j)]
            if matched:
                pairs.append((pi, pj))
            i, j = pi, pj
        agree = matched = 0
        misses = []
        for ti, sj in reversed(pairs):
            mid = (segs[sj][0] + segs[sj][1]) / 2
            note = next((x for x in perf["notes"] if x["t"] <= mid < x["t"] + x["dur"] + 0.02), None)
            if not note:
                continue
            matched += 1
            if _tok_cost(toks[ti], FAM_CENTRE[FAM_OF_SWARA[note["swara"]]]) == 0:
                agree += 1
            else:
                misses.append({"t": round(segs[sj][0], 2), "sung": toks[ti], "transcribed": note["label"]})
        out.append({"start": lab["start"], "end": lab["end"], "syllables": n,
                    "matched": matched, "agree": agree, "misses": misses})
    return out


def report(slug: str) -> dict:
    d = DATA / slug
    perf = json.loads((d / "performance.json").read_text())
    rep = {"slug": slug, "title": perf["title"], "notes": perf["stats"]["note_count"],
           "removed": perf["stats"].get("removed"),
           "coverage": coverage(perf, d / "work" / "vocals.wav"),
           "out_of_raga": out_of_raga(perf)}
    fb = d / "feedback.json"
    rep["feedback"] = feedback_checks(perf, json.loads(fb.read_text())) if fb.exists() else []
    lab = d / "sargam_labels.json"
    if lab.exists():
        rep["sargam"] = sargam_check(perf, d / "work" / "f0.vad.csv", json.loads(lab.read_text()))
    (d / "report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False) + "\n")
    return rep


def _fmt(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


def main() -> int:
    slugs = sys.argv[1:] or sorted(p.parent.name for p in DATA.glob("*/performance.json"))
    for slug in slugs:
        r = report(slug)
        print(f"\n=== {r['title']}  ({slug})")
        c = r["coverage"]
        if c:
            print(f"  voice sounding {c['voice_seconds'] / 60:.1f} min · covered by notes {100 * c['covered']:.0f}% · "
                  f"gaps ≥{MIN_GAP_S}s total {c['gaps_total_seconds']:.0f}s · notes outside voice {c['notes_outside_voice_seconds']}s")
            print("  longest gaps: " + ", ".join(f"{_fmt(g['start'])}–{_fmt(g['end'])}" for g in c["longest_gaps"][:6]))
        else:
            print("  coverage: no local voice stem (run separation first)")
        print(f"  notes {r['notes']} · removed as errors {r['removed']}")
        if r["out_of_raga"] is not None:
            oor = r["out_of_raga"]
            print(f"  held notes outside the raga: {len(oor)}" + (" — " + ", ".join(f"{_fmt(x['t'])} {x['label']}" for x in oor[:6]) if oor else ""))
        if r["feedback"]:
            ok = sum(1 for f in r["feedback"] if f["pass"])
            judged = sum(1 for f in r["feedback"] if f["pass"] is not None)
            print(f"  feedback checks: {ok}/{judged} pass")
            for f in r["feedback"]:
                mark = {True: "✓", False: "✗", None: "·"}[f["pass"]]
                print(f"    {mark} {_fmt(f['start'])}–{_fmt(f['end'])} {f['check']}: {f['measured']}  | {f['text'][:50]}")
        for s in r.get("sargam", []):
            print(f"  sung sargam {_fmt(s['start'])}–{_fmt(s['end'])}: {s['agree']}/{s['matched']} matched syllables agree"
                  + (" — misses: " + ", ".join(f"{_fmt(m['t'])} sung {m['sung']} / transcribed {m['transcribed']}" for m in s["misses"]) if s["misses"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
