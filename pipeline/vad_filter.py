"""Keep vocal frames; drop silence, and tanpura pitches heard outside vocal segments."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np


def _load_f0(path: Path) -> list[tuple[float, float, float]]:
    rows = []
    with path.open() as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                t = float(row["time"])
                hz = float(row["frequency"])
                c = float(row["confidence"])
            except (KeyError, ValueError):
                continue
            rows.append((t, hz, c))
    return rows


def _silero_segments(wav_path: Path) -> list[tuple[float, float]]:
    try:
        import torch

        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            trust_repo=True,
        )
        get_speech_timestamps, _, read_audio, *_ = utils
        wav = read_audio(str(wav_path), sampling_rate=16000)
        stamps = get_speech_timestamps(
            wav,
            model,
            sampling_rate=16000,
            threshold=0.35,
            min_speech_duration_ms=150,
            min_silence_duration_ms=800,
            speech_pad_ms=350,
            return_seconds=True,
        )
        return [(s["start"], s["end"]) for s in stamps]
    except Exception:
        return []


def _energy_segments(wav_path: Path) -> list[tuple[float, float]]:
    import librosa

    y, sr = librosa.load(wav_path, sr=16000, mono=True)
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=256)[0]
    times = librosa.times_like(rms, sr=sr, hop_length=256)
    thr = float(np.median(rms) + 0.4 * np.std(rms))
    voiced = rms > thr
    segs = []
    start = None
    for t, v in zip(times, voiced):
        if v and start is None:
            start = float(t)
        elif not v and start is not None:
            segs.append((start, float(t)))
            start = None
    if start is not None:
        segs.append((start, float(times[-1])))
    return segs


def _in_seg(t: float, segs: list[tuple[float, float]]) -> bool:
    lo, hi = 0, len(segs) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        s, e = segs[mid]
        if t < s:
            hi = mid - 1
        elif t > e:
            lo = mid + 1
        else:
            return True
    return False


def is_drone_harmonic(hz: float, sa_hz: float, tol_cents: float = 20.0) -> bool:
    """True if hz sits on a tanpura string pitch (Sa or Pa in any octave).

    Only meaningful outside vocal segments: a singer holding Sa or Pa lands on
    exactly these pitches, so this must never be used to reject in-speech frames.
    """
    if sa_hz <= 0 or hz <= 0:
        return False
    cents = 1200.0 * math.log2(hz / sa_hz) % 1200.0
    for target in (0.0, 1200.0 * math.log2(1.5), 1200.0):
        if abs(cents - target) < tol_cents:
            return True
    return False


def filter_f0(
    f0_csv: Path,
    vocals_wav: Path,
    out_csv: Path,
    sa_hz: float,
    conf_in_speech: float = 0.45,
    conf_rescue: float = 0.80,
) -> dict:
    rows = _load_f0(f0_csv)
    segs = _silero_segments(vocals_wav) or _energy_segments(vocals_wav)
    kept_speech = kept_rescue = dropped = 0
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "frequency", "confidence"])
        for t, hz, c in rows:
            speech = _in_seg(t, segs) if segs else True
            if speech and c >= conf_in_speech and hz > 50:
                w.writerow([f"{t:.4f}", f"{hz:.4f}", f"{c:.4f}"])
                kept_speech += 1
            elif (
                (not speech)
                and c >= conf_rescue
                and hz > 50
                and not is_drone_harmonic(hz, sa_hz)
            ):
                w.writerow([f"{t:.4f}", f"{hz:.4f}", f"{c:.4f}"])
                kept_rescue += 1
            else:
                dropped += 1
    return {
        "kept_speech": kept_speech,
        "kept_rescue": kept_rescue,
        "dropped": dropped,
        "segments": len(segs),
        "out": str(out_csv),
    }
