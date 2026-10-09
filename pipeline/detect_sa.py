"""Estimate Sa from accompaniment (tanpura) first, then vocal tonic."""

from __future__ import annotations

import json
import math
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


def _madhya_octave(sa: float, voiced: np.ndarray) -> float:
    """The octave of sa whose [Sa, 2 Sa) band (a semitone lower) holds the most singing."""
    if len(voiced) == 0:
        return sa
    lo = 2 ** (-100 / 1200)
    return max(
        (sa * 2.0**k for k in range(-2, 3)),
        key=lambda s: float(((voiced >= s * lo) & (voiced < 2 * s * lo)).mean()),
    )


def _pitch_class_share(voiced: np.ndarray, sa: float, cents: float, tol: float = 50.0) -> float:
    d = (1200.0 * np.log2(voiced / sa) - cents + 600.0) % 1200.0 - 600.0
    return float((np.abs(d) < tol).mean())


def _sa_by_resting_notes(tanpura_cands: list[dict], voiced: np.ndarray) -> dict | None:
    """Sa = the tanpura peak (read as Sa, Pa or Ma) the singing rests on most.

    Score: share of confident singing on Sa, plus half the share on Pa — the
    resting notes of nearly every raga. The most-sung pitch alone is not
    enough (Chhayanat dwells on Re), and a strong tanpura peak is often the
    Pa or Ma string (Jasraj side B: 91.5 Hz is mandra Ma of Sa 137.3). Checked
    on all five recordings: within 12 cents of the established Sa.
    """
    if len(voiced) < 500:
        return None
    best = None
    for rank, t in enumerate(tanpura_cands[:6]):
        for as_what, ratio in (("sa", 1.0), ("pa", 2 / 3), ("ma", 3 / 4)):
            sa = t["hz"] * ratio
            score = _pitch_class_share(voiced, sa, 0.0) + 0.5 * _pitch_class_share(voiced, sa, 702.0)
            if best is None or score > best[0] + 1e-9:
                best = (score, sa, t["hz"], as_what)
    score, sa, peak, as_what = best
    return {"sa_hz": round(_madhya_octave(sa, voiced), 3), "peak": peak, "peak_as": as_what,
            "resting_score": round(score, 3)}


def _sa_by_voice_grid(voiced: np.ndarray, swaras: set[str] | None) -> dict | None:
    """Sa from the singing alone: every 5 cents through an octave, score
    rest-on-Sa (+ half rest-on-Pa) plus, with a raga, the raga-scale fit.

    Tanpura peaks can miss Sa entirely (Bihag / Khadim Hussain Khan: the peaks
    implied 186 Hz; the singing rests on ~139 Hz, where Ga, Ma, Pa and Ni of
    Bihag fall into place). On the seven earlier recordings this lands within
    19 cents of the established Sa; calibration removes the rest.
    """
    if len(voiced) < 500:
        return None
    from .raga import raga_fit

    hz = voiced[:: max(1, len(voiced) // 60000)]

    def near(sa: float, cents: float) -> float:
        # Triangular weight (1 at the swara, 0 at 50 cents) so the score peaks
        # at the centre of the singing rather than anywhere within +-50 cents.
        d = np.abs((1200.0 * np.log2(hz / sa) - cents + 600.0) % 1200.0 - 600.0)
        return float(np.clip(1.0 - d / 50.0, 0.0, None).mean())

    best = None
    for c in np.arange(0.0, 1200.0, 5.0):
        sa = 100.0 * 2.0 ** (c / 1200.0)
        score = near(sa, 0.0) + 0.5 * near(sa, 702.0)
        if swaras:
            score += raga_fit(hz, sa, swaras)
        if best is None or score > best[0]:
            best = (score, sa)
    return {"sa_hz": round(_madhya_octave(best[1], voiced), 3), "score": round(best[0], 3)}


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
    voice_grid = None
    if len(voiced) > 500:
        from .raga import RAGAS

        voice_grid = _sa_by_voice_grid(voiced, RAGAS.get(raga) if raga else None)
        if voice_grid:
            chosen = voice_grid["sa_hz"]
            source = "voice-grid" + (f"+raga:{raga}" if raga else "")
    if raga and tanpura_cands and len(voiced) > 500:
        from .raga import RAGAS, choose_sa

        # Kept for comparison; the voice grid above decides when it ran.
        raga_choice = choose_sa([c["hz"] for c in tanpura_cands], voiced, RAGAS[raga])
        if chosen is None:
            chosen = raga_choice["sa_hz"]
            source = f"tanpura+raga-fit:{raga}"
    # Prefer accompaniment peak that also sits near a vocal tonic (or its octave).
    agreement = None
    if chosen is None and tanpura_cands:
        if vocal_cands:
            agreement = _sa_by_resting_notes(tanpura_cands, voiced)
            if agreement:
                chosen = agreement["sa_hz"]
                source = f"tanpura({agreement['peak_as']})+resting-notes"
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
        "agreement": agreement,
        "voice_grid": voice_grid,
        "note": "Pin this in the player if the drone sounds off. Labels remap from stored Hz.",
    }


def write_estimate(result: dict, path: Path) -> None:
    path.write_text(json.dumps(result, indent=2))
