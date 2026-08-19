"""Group a filtered f0 track into Hz-first sargam notes."""

from __future__ import annotations

import csv
import json
import math
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

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


def frames_to_notes(
    frames: list[Frame],
    sa_hz: float,
    gap_tol: float = 0.06,
    min_dur: float = 0.035,
    max_cents_for_merge: float = 45.0,
) -> list[Note]:
    frames = _deglitch(frames, sa_hz)
    frames = _median_smooth(frames, 5)
    if not frames:
        return []

    labeled = []
    for f in frames:
        hit = nearest_swara(f.hz, sa_hz)
        labeled.append((f, hit))

    notes: list[Note] = []
    acc_hz: list[float] = []
    acc_conf: list[float] = []
    f0, h0 = labeled[0]
    start = end = f0.t
    acc_hz.append(f0.hz)
    acc_conf.append(f0.conf)
    cur_sw, cur_oct = h0.swara, h0.octave

    def flush(t0: float, t1: float, sw: str, octv: int) -> None:
        if not acc_hz:
            return
        dur = (t1 - t0) + 0.01
        if dur < min_dur:
            return
        # confidence-weighted mean Hz
        w = [max(0.05, c) for c in acc_conf]
        hz = sum(h * wi for h, wi in zip(acc_hz, w)) / sum(w)
        hit = nearest_swara(hz, sa_hz)
        # snap quality: 1 at 0 cents, 0 at 50 cents
        snap = max(0.0, 1.0 - abs(hit.cents_off) / 50.0)
        mean_conf = sum(acc_conf) / len(acc_conf)
        notes.append(
            Note(
                t=round(t0, 3),
                dur=round(dur, 3),
                hz=round(hz, 3),
                conf=round(mean_conf * snap, 4),
                cents_off=round(hit.cents_off, 2),
                swara=hit.swara,
                octave=hit.octave,
                label=hit.label,
                snap_quality=round(snap, 4),
            )
        )

    for f, hit in labeled[1:]:
        same = hit.swara == cur_sw and abs(hit.octave - cur_oct) <= 1
        close = abs(hit.cents_off) <= max_cents_for_merge
        if same and close and (f.t - end) <= gap_tol:
            end = f.t
            acc_hz.append(f.hz)
            acc_conf.append(f.conf)
        else:
            flush(start, end, cur_sw, cur_oct)
            acc_hz = [f.hz]
            acc_conf = [f.conf]
            start = end = f.t
            cur_sw, cur_oct = hit.swara, hit.octave
    flush(start, end, cur_sw, cur_oct)
    return notes


def write_performance(
    notes: list[Note],
    dest: Path,
    *,
    title: str,
    audio_rel: str,
    sa_hz: float,
    sa_meta: dict,
    extra: dict | None = None,
) -> None:
    payload = {
        "schema": "hindustani-notation-v1",
        "title": title,
        "audio": audio_rel,
        "sa_hz": sa_hz,
        "sa_source": sa_meta.get("sa_source"),
        "sa_estimate": sa_meta,
        "swara_system": "just",
        "notes": [asdict(n) for n in notes],
        "stats": {
            "note_count": len(notes),
            "mean_abs_cents": round(
                statistics.mean(abs(n.cents_off) for n in notes) if notes else 0.0, 2
            ),
            "mean_conf": round(
                statistics.mean(n.conf for n in notes) if notes else 0.0, 4
            ),
            "low_conf_notes": sum(1 for n in notes if n.conf < 0.35),
        },
    }
    if extra:
        payload["pipeline"] = extra
    dest.write_text(json.dumps(payload, indent=2))
