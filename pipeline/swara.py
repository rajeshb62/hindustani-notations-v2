"""Just-intonation swara set shared by transcriber and (documented for) the player."""

from __future__ import annotations

import math
from dataclasses import dataclass

# Ratios relative to Sa. These are what the player synthesizes.
JUST_RATIOS: dict[str, float] = {
    "S": 1,
    "r": 256 / 243,
    "R": 9 / 8,
    "g": 32 / 27,
    "G": 5 / 4,
    "M": 4 / 3,
    "M+": 45 / 32,
    "P": 3 / 2,
    "d": 128 / 81,
    "D": 5 / 3,
    "n": 16 / 9,
    "N": 15 / 8,
}

SWARA_CENTS: dict[str, float] = {
    name: 1200.0 * math.log2(ratio) for name, ratio in JUST_RATIOS.items()
}

NAMES = {
    "S": "Sa",
    "r": "Re komal",
    "R": "Re shuddh",
    "g": "Ga komal",
    "G": "Ga shuddh",
    "M": "Ma shuddh",
    "M+": "Ma tivra",
    "P": "Pa",
    "d": "Dha komal",
    "D": "Dha shuddh",
    "n": "Ni komal",
    "N": "Ni shuddh",
}


@dataclass(frozen=True)
class SwaraHit:
    swara: str
    octave: int
    cents_off: float
    ideal_hz: float
    label: str


def hz_to_cents(hz: float, sa_hz: float) -> float:
    return 1200.0 * math.log2(hz / sa_hz)


def nearest_swara(hz: float, sa_hz: float) -> SwaraHit:
    if hz <= 0 or sa_hz <= 0:
        raise ValueError("hz and sa_hz must be positive")
    cents = hz_to_cents(hz, sa_hz)
    octave = math.floor(cents / 1200.0)
    local = cents - octave * 1200.0
    best_name = "S"
    best_err = 999.0
    best_oct = octave
    for name, sw_cents in SWARA_CENTS.items():
        err = local - sw_cents
        cand_oct = octave
        # wrap near next Sa
        if name == "S":
            wrap = local - 1200.0
            if abs(wrap) < abs(err):
                err = wrap
                cand_oct = octave + 1
        if abs(err) < abs(best_err):
            best_err = err
            best_name = name
            best_oct = cand_oct
    ideal = sa_hz * JUST_RATIOS[best_name] * (2.0 ** best_oct)
    if best_oct > 0:
        label = best_name + ("'" * best_oct)
    elif best_oct < 0:
        label = best_name + ("." * abs(best_oct))
    else:
        label = best_name
    return SwaraHit(best_name, best_oct, best_err, ideal, label)
