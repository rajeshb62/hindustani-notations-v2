"""Estimate Sa from accompaniment (tanpura) first, then vocal tonic."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def _stft_peak_scores(y: np.ndarray, sr: int, lo: float = 70.0, hi: float = 280.0) -> list[dict]:
    import librosa

    hop = 2048
    n_fft = 8192
    spec = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop))
    mag = spec.mean(axis=1)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    band = (freqs >= lo) & (freqs <= hi)
    f = freqs[band]
    m = mag[band]
    if len(m) == 0:
        return []
    m = m / (m.max() + 1e-12)

    # Harmonic product: a true Sa should have energy at 2x,3x,4x,5x.
    scores = []
    for i, fund in enumerate(f):
        harm = 0.0
        for k in (1, 2, 3, 4, 5):
            target = fund * k
            j = int(np.argmin(np.abs(freqs - target)))
            harm += float(mag[j]) / k
        scores.append((float(fund), float(harm), float(m[i])))

    scores.sort(key=lambda x: x[1], reverse=True)
    # Peak-pick: keep local maxima among top region
    out = []
    used = []
    for fund, harm, local in scores[:80]:
        if any(abs(fund - u) < 1.5 for u in used):
            continue
        used.append(fund)
        out.append({"hz": round(fund, 3), "harmonic_score": round(harm, 4), "band_energy": round(local, 4)})
        if len(out) >= 8:
            break
    return out


def _vocal_tonic_histogram(f0_hz: np.ndarray, lo: float = 70.0) -> list[dict]:
    # Pitch class only: folded into one octave, so the tanpura (or a pin) picks
    # the register. Male Sa ~100-150 Hz, female ~200-280 Hz.
    hi = 2.0 * lo
    voiced = f0_hz[(f0_hz > 50) & np.isfinite(f0_hz)]
    if len(voiced) < 20:
        return []
    folded = []
    for hz in voiced:
        x = float(hz)
        while x >= hi:
            x /= 2.0
        while x < lo:
            x *= 2.0
        if lo <= x < hi:
            folded.append(x)
    if not folded:
        return []
    hist, edges = np.histogram(folded, bins=80, range=(lo, hi))
    centers = 0.5 * (edges[:-1] + edges[1:])
    order = np.argsort(hist)[::-1]
    out = []
    used = []
    for i in order:
        hz = float(centers[i])
        if any(abs(hz - u) < 1.8 for u in used):
            continue
        used.append(hz)
        out.append({"hz": round(hz, 3), "count": int(hist[i])})
        if len(out) >= 6:
            break
    return out


def estimate_sa(
    accompaniment_wav: Path | None = None,
    mix_wav: Path | None = None,
    f0_csv: Path | None = None,
    sr: int = 22050,
    raga: str | None = None,
) -> dict:
    """Sa from tanpura peaks, cross-checked against the voice.

    With `raga`, the tanpura peak (as Sa, Pa or Ma, any octave) that puts the
    confident singing on that raga's swaras wins; see raga.py.
    """
    import librosa

    tanpura_cands: list[dict] = []
    src = accompaniment_wav if accompaniment_wav and accompaniment_wav.exists() else mix_wav
    source_name = None
    if src and Path(src).exists():
        source_name = str(src)
        y, file_sr = librosa.load(src, sr=sr, mono=True, duration=90.0)
        tanpura_cands = _stft_peak_scores(y, file_sr)

    vocal_cands: list[dict] = []
    voiced = np.array([])
    if f0_csv and Path(f0_csv).exists():
        rows = np.genfromtxt(f0_csv, delimiter=",", names=True)
        if rows.dtype.names and "frequency" in rows.dtype.names:
            vocal_cands = _vocal_tonic_histogram(np.asarray(rows["frequency"], dtype=float))
            hz = np.asarray(rows["frequency"], dtype=float)
            conf = np.asarray(rows["confidence"], dtype=float)
            voiced = hz[(conf >= 0.8) & (hz > 60)]

    chosen = None
    source = "unresolved"
    raga_choice = None
    if raga and tanpura_cands and len(voiced) > 500:
        from .raga import RAGAS, choose_sa

        raga_choice = choose_sa([c["hz"] for c in tanpura_cands], voiced, RAGAS[raga])
        chosen = raga_choice["sa_hz"]
        source = f"tanpura+raga-fit:{raga}"
    # Prefer accompaniment peak that also sits near a vocal tonic (or its octave).
    if chosen is None and tanpura_cands:
        if vocal_cands:
            best = None
            best_d = 1e9
            for t in tanpura_cands[:5]:
                for v in vocal_cands[:4]:
                    for k in (0.5, 1.0, 2.0):
                        d = abs(t["hz"] - v["hz"] * k)
                        if d < best_d:
                            best_d = d
                            best = t
            if best and best_d < 4.0:
                chosen = best["hz"]
                source = "tanpura+vocal-agreement"
        if chosen is None:
            chosen = tanpura_cands[0]["hz"]
            source = "tanpura-harmonic"
    elif chosen is None and vocal_cands:
        chosen = vocal_cands[0]["hz"]
        source = "vocal-tonic-histogram"

    return {
        "sa_hz": None if chosen is None else round(float(chosen), 3),
        "sa_source": source,
        "audio_used": source_name,
        "tanpura_candidates": tanpura_cands,
        "vocal_tonic_candidates": vocal_cands,
        "raga": raga,
        "raga_choice": raga_choice,
        "note": "Pin this in the player if the drone sounds off. Labels remap from stored Hz.",
    }


def write_estimate(result: dict, path: Path) -> None:
    path.write_text(json.dumps(result, indent=2))
