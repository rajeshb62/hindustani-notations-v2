"""Group a filtered f0 track into Hz-first sargam notes."""

from __future__ import annotations

import bisect
import csv
import json
import math
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

from .swara import JUST_RATIOS as JUST_ORDER
from .swara import nearest_swara


@dataclass
class Frame:
    t: float
    hz: float
    conf: float


@dataclass
class Note:
    t: float
    dur: float
    hz: float
    conf: float
    cents_off: float
    swara: str
    octave: int
    label: str
    snap_quality: float
    # None = a note. Otherwise why it is an error, not something the singer
    # sang: "range" (flag_range: bleed / 2nd harmonic) or "octave"
    # (flag_octave_flips). Players hide flagged notes.
    flag: str | None = None


def load_frames(path: Path) -> list[Frame]:
    frames: list[Frame] = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                hz = float(row["frequency"])
                if hz <= 50:
                    continue
                frames.append(
                    Frame(float(row["time"]), hz, float(row["confidence"]))
                )
            except (KeyError, ValueError):
                continue
    frames.sort(key=lambda x: x.t)
    return frames


def _deglitch(frames: list[Frame], sa_hz: float, window_sec: float = 1.4) -> list[Frame]:
    if not frames:
        return []
    cents = [1200.0 * math.log2(f.hz / sa_hz) for f in frames]
    times = [f.t for f in frames]
    out_cents = []
    left = right = 0
    n = len(cents)
    for i, t in enumerate(times):
        while left < n and times[left] < t - window_sec:
            left += 1
        while right < n and times[right] <= t + window_sec:
            right += 1
        local = cents[left:right]
        ref = statistics.median(local) if local else cents[i]
        cands = [cents[i] + 1200.0 * k for k in range(-3, 4)]
        best = min(cands, key=lambda x: abs(x - ref))
        if abs(cents[i] - ref) > 650 and abs(best - ref) + 80 < abs(cents[i] - ref):
            out_cents.append(best)
        else:
            out_cents.append(cents[i])
    return [
        Frame(f.t, sa_hz * (2 ** (c / 1200.0)), f.conf)
        for f, c in zip(frames, out_cents)
    ]


def _median_smooth(frames: list[Frame], win: int = 5) -> list[Frame]:
    if win < 3 or len(frames) < win:
        return frames
    if win % 2 == 0:
        win += 1
    half = win // 2
    hz = [f.hz for f in frames]
    out = []
    for i, f in enumerate(frames):
        sl = hz[max(0, i - half) : min(len(hz), i + half + 1)]
        out.append(Frame(f.t, statistics.median(sl), f.conf))
    return out


def prepare_frames(frames: list[Frame], sa_hz: float) -> list[Frame]:
    """Fix octave hops, then remove single-frame spikes.

    The 3-frame median only kills 1-frame glitches; anything longer (kan swaras,
    gamak) survives. A wider window erased real 20 ms ornaments.
    """
    return _median_smooth(_deglitch(frames, sa_hz), 3)


# Frame times are 10 ms steps in float; 0.02 can come out as 0.01999.
_EPS = 1e-6


@dataclass
class _Group:
    t0: float
    t1: float
    swara: str
    octave: int
    hz: list[float]
    conf: list[float]

    @property
    def dur(self) -> float:
        return (self.t1 - self.t0) + 0.01


def _merge_bridges(groups: list[_Group], bridge_max: float, gap_max: float) -> list[_Group]:
    """A-x-A → A when x is a sub-`bridge_max` flicker inside a held note.

    Ported from the legacy postprocess_notation.py that produced the known-good
    by-ear result. Repeats until stable.
    """
    changed = True
    while changed:
        changed = False
        out: list[_Group] = []
        i = 0
        while i < len(groups):
            if i + 2 < len(groups):
                a, x, b = groups[i], groups[i + 1], groups[i + 2]
                if (
                    a.swara == b.swara
                    and a.octave == b.octave
                    and x.dur + _EPS < bridge_max
                    and b.t0 - (a.t0 + a.dur) <= gap_max
                ):
                    out.append(_Group(a.t0, b.t1, a.swara, a.octave, a.hz + b.hz, a.conf + b.conf))
                    i += 3
                    changed = True
                    continue
            out.append(groups[i])
            i += 1
        groups = out
    return groups


def frames_to_notes(
    frames: list[Frame],
    sa_hz: float,
    gap_tol: float = 0.075,
    min_dur: float = 0.020,
    max_cents_for_merge: float = 45.0,
    bridge_max: float = 0.020,
    bridge_gap: float = 0.085,
    *,
    prepared: bool = False,
    positions: dict[str, float] | None = None,
) -> list[Note]:
    # `positions`: swara cents measured for this performance (calibrate.py);
    # None = the just-intonation table.
    # Defaults follow the by-ear known-good pipeline (gap 0.0748, bridge merge,
    # then a 20 ms floor). Two-frame kan swaras survive; lone frames do not.
    if not prepared:
        frames = prepare_frames(frames, sa_hz)
    if not frames:
        return []

    groups: list[_Group] = []
    cur: _Group | None = None
    for f in frames:
        hit = nearest_swara(f.hz, sa_hz, positions)
        # Same swara in a different octave is a different note; merging across
        # octaves over-smooths and sounded worse by ear.
        if (
            cur is not None
            and hit.swara == cur.swara
            and hit.octave == cur.octave
            and abs(hit.cents_off) <= max_cents_for_merge
            and (f.t - cur.t1) <= gap_tol
        ):
            cur.t1 = f.t
            cur.hz.append(f.hz)
            cur.conf.append(f.conf)
        else:
            cur = _Group(f.t, f.t, hit.swara, hit.octave, [f.hz], [f.conf])
            groups.append(cur)

    groups = _merge_bridges(groups, bridge_max, bridge_gap)

    notes: list[Note] = []
    for g in groups:
        if g.dur + _EPS < min_dur:
            continue
        # confidence-weighted mean Hz
        w = [max(0.05, c) for c in g.conf]
        hz = sum(h * wi for h, wi in zip(g.hz, w)) / sum(w)
        hit = nearest_swara(hz, sa_hz, positions)
        # snap quality: 1 at 0 cents, 0 at 50 cents
        snap = max(0.0, 1.0 - abs(hit.cents_off) / 50.0)
        mean_conf = sum(g.conf) / len(g.conf)
        notes.append(
            Note(
                t=round(g.t0, 3),
                dur=round(g.dur, 3),
                hz=round(hz, 3),
                conf=round(mean_conf * snap, 4),
                cents_off=round(hit.cents_off, 2),
                swara=hit.swara,
                octave=hit.octave,
                label=hit.label,
                snap_quality=round(snap, 4),
            )
        )
    return flag_octave_flips(flag_range(notes, sa_hz), sa_hz)


def singer_range(
    notes: list[Note], sa_hz: float, margin: float = 500.0, short: float = 0.080
) -> tuple[float, float]:
    """(low, high) cents from Sa the singer plausibly reaches.

    Time-weighted 1st-99th percentile of trusted notes, widened by `margin`
    (5 semitones). Relative to each singer: ICCR really does sing two octaves
    above its Sa, Jasraj almost never does.
    """
    # Skip short notes caught between swaras (>25 cents off): thousands of
    # glide fragments otherwise stretch the percentiles enough to admit bleed
    # (Paluskar's r'' at 2521 cents sits right at the edge).
    pts = sorted(
        (1200.0 * math.log2(n.hz / sa_hz), n.dur)
        for n in notes
        if n.flag in (None, "range")
        and not (n.dur + _EPS < short and abs(n.cents_off) > 25.0)
    )
    if not pts:
        return (-math.inf, math.inf)
    total = sum(w for _, w in pts)

    def pct(p: float) -> float:
        acc = 0.0
        for c, w in pts:
            acc += w
            if acc >= p * total:
                return c
        return pts[-1][0]

    return (pct(0.01) - margin, pct(0.99) + margin)


def flag_range(notes: list[Note], sa_hz: float, margin: float = 500.0) -> list[Note]:
    """Flag notes outside the singer's own range, whatever their length.

    These are an accompanying instrument (harmonium/sarangi doubling Sa an
    octave up) or the tracker locking onto the voice's 2nd harmonic — e.g.
    Jasraj side A 25:33, where held S' keeps jumping to S'' at exactly 2x.
    """
    lo, hi = singer_range(notes, sa_hz, margin)
    for n in notes:
        c = 1200.0 * math.log2(n.hz / sa_hz)
        if n.flag is None and not (lo <= c <= hi):
            n.flag = "range"
    return notes


def flag_octave_flips(
    notes: list[Note],
    sa_hz: float,
    short: float = 0.080,
    tol: float = 60.0,
    gap: float = 0.075,
) -> list[Note]:
    """Flag short notes that flicker exactly an octave away from their neighbour.

    E.g. Jasraj side A 21:46: P → M/M'/M/M' every 20-30 ms → P. No singer jumps
    an octave for 20 ms and back; it is bleed or a tracker harmonic. Grow the
    alternating cluster, then keep the octave that fits the notes just before
    and after it (P→M→P is a step, P→M'→P is a 1000-cent leap) and flag the other.
    """
    cents = [1200.0 * math.log2(n.hz / sa_hz) for n in notes]

    def joined(i: int, j: int) -> bool:
        a, b = notes[min(i, j)], notes[max(i, j)]
        return b.t - (a.t + a.dur) <= gap

    def octave_apart(i: int, j: int) -> bool:
        return abs(abs(cents[i] - cents[j]) - 1200.0) <= tol

    i = 0
    while i + 1 < len(notes):
        a, b = notes[i], notes[i + 1]
        if not (
            joined(i, i + 1)
            and octave_apart(i, i + 1)
            and min(a.dur, b.dur) + _EPS < short
            and "range" not in (a.flag, b.flag)
        ):
            i += 1
            continue
        low, high = sorted((cents[i], cents[i + 1]))

        def on_level(k: int) -> bool:
            return (
                notes[k].dur + _EPS < short
                and notes[k].flag != "range"
                and (abs(cents[k] - low) <= tol or abs(cents[k] - high) <= tol)
            )

        lo_i, hi_i = i, i + 1
        while lo_i - 1 >= 0 and joined(lo_i - 1, lo_i) and on_level(lo_i - 1):
            lo_i -= 1
        while hi_i + 1 < len(notes) and joined(hi_i, hi_i + 1) and on_level(hi_i + 1):
            hi_i += 1
        refs = [cents[k] for k in (lo_i - 1, hi_i + 1)
                if 0 <= k < len(notes) and joined(k, lo_i if k < lo_i else hi_i)]
        if refs:
            ref = sum(refs) / len(refs)
            bad = high if abs(high - ref) > abs(low - ref) else low
            for k in range(lo_i, hi_i + 1):
                if abs(cents[k] - bad) <= tol and notes[k].dur + _EPS < short:
                    notes[k].flag = "octave"
        i = hi_i + 1
    return notes


def _in_spans(t: float, c: float, spans: list[tuple[float, float, float | None]]) -> bool:
    """True if a frame at time t / pitch c falls in an error span.

    Spans are (start, end, level): level None drops everything in the span;
    otherwise only frames within 60 cents of that pitch (the flip's octave).
    """
    k = bisect.bisect_right(spans, (t, math.inf, math.inf))
    for s0, s1, level in spans[max(0, k - 3):k]:
        if s0 - _EPS <= t <= s1 + _EPS and (level is None or abs(c - level) <= 60.0):
            return True
    return False


def error_spans(notes: list[Note], sa_hz: float) -> list[tuple[float, float, float | None]]:
    """Where the pitch curve must stay silent: notes flagged as errors.

    Out-of-range notes drop their whole span. Octave flips drop only frames at
    the flipped pitch, widened by a few frames: flicker fragments too short to
    become notes still sit at that pitch just beside them.
    """
    spans: list[tuple[float, float, float | None]] = []
    for n in notes:
        if n.flag == "range":
            spans.append((n.t, n.t + n.dur - 0.01, None))
        elif n.flag in ("octave", "listener"):
            spans.append((n.t - 0.04, n.t + n.dur + 0.04, 1200.0 * math.log2(n.hz / sa_hz)))
    return sorted(spans)


def build_contour(
    frames: list[Frame],
    sa_hz: float,
    cents_range: tuple[float, float] | None = None,
    drop: list[tuple[float, float, float | None]] | None = None,
) -> dict:
    """Pitch curve for glide-faithful playback: runs of whole cents above Sa.

    Each run is [start_time, [cents, ...]] sampled every `step` seconds; a gap
    longer than 1.5 steps starts a new run (the player treats it as silence).
    Frames outside `cents_range` (see singer_range), or inside a `drop`
    interval (notes flagged range/octave), are left out as silence.
    """
    if not frames:
        return {"step": 0.01, "runs": []}
    diffs = sorted(b.t - a.t for a, b in zip(frames, frames[1:]) if b.t > a.t)
    step = round(diffs[len(diffs) // 2], 4) if diffs else 0.01
    runs: list[list] = []
    prev_t = None
    for f in frames:
        c = round(1200.0 * math.log2(f.hz / sa_hz))
        if cents_range and not (cents_range[0] <= c <= cents_range[1]):
            continue
        if drop and _in_spans(f.t, c, drop):
            continue
        if prev_t is None or f.t - prev_t > 1.5 * step:
            runs.append([round(f.t, 3), [c]])
        else:
            runs[-1][1].append(c)
        prev_t = f.t
    return {"step": step, "runs": runs}


def write_performance(
    notes: list[Note],
    dest: Path,
    *,
    title: str,
    audio_rel: str,
    sa_hz: float,
    sa_meta: dict,
    extra: dict | None = None,
    contour: dict | None = None,
    calibration: dict | None = None,
    raga: str | None = None,
) -> None:
    """`notes` must still include flagged errors: build the contour's
    error_spans from them first. They are dropped here."""
    kept = [n for n in notes if n.flag is None]
    removed = [n for n in notes if n.flag is not None]
    payload = {
        "schema": "hindustani-notation-v1",
        "title": title,
        "audio": audio_rel,
        "sa_hz": sa_hz,
        "sa_source": sa_meta.get("sa_source"),
        "sa_estimate": sa_meta,
        "swara_system": "measured" if calibration else "just",
        # Errors (flag_range / flag_octave_flips) are removed from the
        # transcription; only an audit list of what was removed is kept.
        "notes": [{k: v for k, v in asdict(n).items() if k != "flag"} for n in kept],
        "removed_notes": [[n.t, n.dur, n.label, n.flag] for n in removed],
        "stats": {
            "note_count": len(kept),
            "mean_abs_cents": round(
                statistics.mean(abs(n.cents_off) for n in kept) if kept else 0.0, 2
            ),
            "mean_conf": round(
                statistics.mean(n.conf for n in kept) if kept else 0.0, 4
            ),
            "low_conf_notes": sum(1 for n in kept if n.conf < 0.35),
            "removed": {
                k: sum(1 for n in removed if n.flag == k) for k in ("range", "octave", "listener")
            },
        },
    }
    if raga:
        from .raga import RAGAS

        # Check, not constraint: how much trusted, held singing sits on the
        # raga's swaras, and which other swaras appear (and for how long).
        held = [n for n in notes if n.flag is None and n.dur >= 0.15]
        total = sum(n.dur for n in held) or 1.0
        outside: dict[str, float] = {}
        for n in held:
            if n.swara not in RAGAS[raga]:
                outside[n.swara] = outside.get(n.swara, 0.0) + n.dur
        payload["raga"] = raga
        payload["raga_check"] = {
            "swaras": sorted(RAGAS[raga], key=list(JUST_ORDER).index),
            "held_time_on_raga": round(1 - sum(outside.values()) / total, 4),
            "outside_seconds": {k: round(v, 1) for k, v in sorted(outside.items(), key=lambda kv: -kv[1])},
        }
    if calibration:
        # Cents above Sa the player uses to label and synthesize each swara.
        payload["swara_positions"] = calibration["positions"]
        payload["calibration"] = calibration
    if contour:
        payload["contour"] = contour
    if extra:
        payload["pipeline"] = extra
    # Compact separators: the contour alone is ~100k numbers.
    dest.write_text(json.dumps(payload, separators=(",", ":")))
