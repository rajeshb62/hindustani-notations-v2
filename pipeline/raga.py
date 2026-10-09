"""Raga scales (swara sets only — not the full grammar of chalan/pakad).

Used to pick Sa when the tanpura is ambiguous: a tanpura peak can be Sa, Pa
or Ma, and an octave either way. The right Sa is the one that puts the
singing on the raga's swaras (Paluskar's Todi: 92% at Sa=161.5 Hz vs 44% at
the tanpura's strongest peak, which was Pa).
"""

from __future__ import annotations

import math

import numpy as np

NAMES = ["S", "r", "R", "g", "G", "M", "M+", "P", "d", "D", "n", "N"]

RAGAS: dict[str, set[str]] = {
    "todi": {"S", "r", "g", "M+", "P", "d", "N"},  # Miyan ki Todi
    "bhairav": {"S", "r", "G", "M", "P", "d", "N"},
    "bhairavi": {"S", "r", "g", "M", "P", "d", "n"},
    "yaman": {"S", "R", "G", "M+", "P", "D", "N"},
    "bilawal": {"S", "R", "G", "M", "P", "D", "N"},
    "alhaiya-bilawal": {"S", "R", "G", "M", "P", "D", "n", "N"},
    "khamaj": {"S", "R", "G", "M", "P", "D", "n", "N"},
    "kafi": {"S", "R", "g", "M", "P", "D", "n"},
    "asavari": {"S", "R", "g", "M", "P", "d", "n"},
    "darbari": {"S", "R", "g", "M", "P", "d", "n"},
    "marwa": {"S", "r", "G", "M+", "D", "N"},
    "purvi": {"S", "r", "G", "M", "M+", "P", "d", "N"},
    "malkauns": {"S", "g", "M", "d", "n"},
    "bhimpalasi": {"S", "R", "g", "M", "P", "D", "n"},
    "bageshri": {"S", "R", "g", "M", "P", "D", "n"},
    "desh": {"S", "R", "G", "M", "P", "D", "n", "N"},
    "chhayanat": {"S", "R", "G", "M", "M+", "P", "D", "N"},  # tivra Ma as an accidental
    "shuddh-kalyan": {"S", "R", "G", "M+", "P", "D", "N"},  # M+ and N sparing
    "bihag": {"S", "R", "G", "M", "M+", "P", "D", "N"},  # tivra Ma as an accent; R, D weak in aroh
}


def swara_class(hz: np.ndarray, sa_hz: float) -> np.ndarray:
    """Index into NAMES of the nearest 100-cent swara class (octave-folded)."""
    cents = (1200.0 * np.log2(hz / sa_hz)) % 1200.0
    return (((cents + 50.0) % 1200.0) // 100.0).astype(int)


def raga_fit(hz: np.ndarray, sa_hz: float, swaras: set[str]) -> float:
    """Fraction of voiced frames whose swara class is in the raga."""
    if len(hz) == 0:
        return 0.0
    allowed = np.array([n in swaras for n in NAMES])
    return float(allowed[swara_class(hz, sa_hz)].mean())


def choose_sa(candidates: list[float], hz: np.ndarray, swaras: set[str]) -> dict:
    """Best Sa for this raga among tanpura peaks read as Sa, Pa or Ma.

    Octave: the one whose [Sa, 2 Sa) band (widened a semitone down) holds the
    most singing, i.e. treat the voice's main register as madhya saptak.
    """
    tried = []
    for c in candidates:
        for as_what, ratio in (("sa", 1.0), ("pa", 2 / 3), ("ma", 3 / 4)):
            sa = c * ratio
            tried.append({"hz": round(sa, 3), "peak": c, "peak_as": as_what,
                          "fit": round(raga_fit(hz, sa, swaras), 4)})
    # Near-ties (within 1%) go to the stronger tanpura peak: candidates are
    # tried in tanpura-score order, so take the first one close to the best.
    top = max(x["fit"] for x in tried)
    best = next(x for x in tried if x["fit"] >= top - 0.01)
    sa = best["hz"]
    lo_semitone = 2 ** (-100 / 1200)
    octs = []
    for k in range(-2, 3):
        s = sa * 2.0**k
        share = float(((hz >= s * lo_semitone) & (hz < 2 * s * lo_semitone)).mean())
        octs.append((share, s))
    share, sa = max(octs)
    return {"sa_hz": round(sa, 3), "fit": best["fit"], "madhya_share": round(share, 3),
            "candidates": sorted(tried, key=lambda x: -x["fit"])[:8]}
