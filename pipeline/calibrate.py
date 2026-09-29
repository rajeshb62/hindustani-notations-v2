"""Fit Sa and the swara positions to this performance.

The just table is a starting point, not how any singer sings: Jasraj side A
holds komal Ga at ~310 cents (table 294), komal Dha at ~808 (792), and every
held Sa and Pa ~8 cents sharp of the pinned Sa. Intonation depends on raga
and singer, so positions are measured per performance, from its own held,
trusted notes:

1. Sa: the median offset of held Sa and Pa (the fixed reference swaras) is a
   Sa error, not intonation, so shift Sa by it.
2. Other swaras: median of their held notes, clamped to +/-30 cents of the
   table so a bad batch cannot turn one swara into its neighbour. Swaras with
   too few held notes keep the table value.
3. Relabel everything against the measured positions.
"""

from __future__ import annotations

import statistics

from .swara import SWARA_CENTS
from .transcribe import Frame, Note, frames_to_notes

FIXED = ("S", "P")


def _held(notes: list[Note], min_dur: float) -> list[Note]:
    return [n for n in notes if n.flag is None and n.dur >= min_dur]


def refine_sa(
    notes: list[Note], sa_hz: float, min_notes: int = 20, min_dur: float = 0.15
) -> tuple[float, dict]:
    held = [n for n in _held(notes, min_dur) if n.swara in FIXED]
    if len(held) < min_notes:
        return sa_hz, {"shift_cents": 0.0, "n": len(held), "applied": False}
    shift = statistics.median(n.cents_off for n in held)
    return (
        sa_hz * 2.0 ** (shift / 1200.0),
        {"shift_cents": round(shift, 2), "n": len(held), "applied": True},
    )


def measure_positions(
    notes: list[Note],
    min_notes: int = 8,
    min_dur: float = 0.15,
    clamp: float = 30.0,
) -> tuple[dict[str, float], dict[str, dict]]:
    positions: dict[str, float] = {}
    meta: dict[str, dict] = {}
    held = _held(notes, min_dur)
    for sw, table in SWARA_CENTS.items():
        offs = [n.cents_off for n in held if n.swara == sw]
        if sw in FIXED or len(offs) < min_notes:
            positions[sw] = round(table, 1)
            meta[sw] = {"source": "fixed" if sw in FIXED else "table", "n": len(offs)}
            continue
        off = max(-clamp, min(clamp, statistics.median(offs)))
        positions[sw] = round(table + off, 1)
        meta[sw] = {"source": "measured", "n": len(offs), "shift_cents": round(off, 1)}
    return positions, meta


def calibrated_notes(
    frames: list[Frame], sa_pin: float
) -> tuple[list[Note], float, dict]:
    """frames must already be prepare_frames()'d. Returns notes, Sa, calibration."""
    first = frames_to_notes(frames, sa_pin, prepared=True)
    sa_hz, sa_info = refine_sa(first, sa_pin)
    table_notes = frames_to_notes(frames, sa_hz, prepared=True)
    positions, pos_meta = measure_positions(table_notes)
    notes = frames_to_notes(frames, sa_hz, prepared=True, positions=positions)
    return notes, sa_hz, {
        "sa_pin_hz": sa_pin,
        "sa_refine": sa_info,
        "positions": positions,
        "swaras": pos_meta,
    }
