"""Keep pitch frames only where the separated voice track is actually sounding.

Earlier this used Silero VAD, a speech detector. On sung performances it
dropped long held vowels as "not speech" (Desh 0:20-0:41: ~70% of confidently
tracked singing discarded) while letting faint accompaniment residue through
(Desh 0:02-0:14, no voice: 25 notes). The voice stem's own loudness separates
those cases: relative to the stem's 95th percentile, singing sits around
-49 dB median and silence-with-residue around -65 dB. Frames above GATE_DB,
with a short hangover so onsets and note tails are not clipped, are kept.

With RoFormer stems (isolate.py) voice and residue are far apart: on the
listener-labelled stretches singing sits at ~-4 dB and no-voice stretches at
-40 to -75 dB. -30 dB keeps 95.6-98.9% of confidently pitched frames in every
recording while letting through 10% of labelled no-voice frames (-55 dB, tuned
on the noisier Demucs stems, let 38% through).

Known gap: a voice-like instrument the separator keeps in the voice stem
(sarangi, confirmed by ear: Paluskar 10:49-10:58) is as loud as singing; loudness cannot help.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

HOP_S = 0.01         # matches the 10 ms pitch frames
GATE_DB = -30.0      # relative to the voice stem's 95th-percentile level
HANGOVER_S = 0.10    # keep this much either side of active frames


def voice_activity(vocals_wav: Path, gate_db: float = GATE_DB) -> tuple[np.ndarray, dict]:
    """Boolean activity per 10 ms frame of the voice stem, and level stats."""
    import librosa

    y, sr = librosa.load(vocals_wav, sr=16000, mono=True)
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=int(sr * HOP_S))[0]
    db = 20.0 * np.log10(rms + 1e-9)
    ref = float(np.percentile(db, 95))
    active = (db - ref) > gate_db
    k = int(round(HANGOVER_S / HOP_S))
    active = np.convolve(active.astype(float), np.ones(2 * k + 1), mode="same") > 0
    return active, {"ref_db": round(ref, 1), "gate_db": gate_db, "active_share": round(float(active.mean()), 3)}


def filter_f0(
    f0_csv: Path,
    vocals_wav: Path,
    out_csv: Path,
    sa_hz: float | None = None,
    conf_min: float = 0.45,
) -> dict:
    active, level = voice_activity(vocals_wav)
    kept = dropped_silent = dropped_conf = 0
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with f0_csv.open() as fin, out_csv.open("w", newline="") as fout:
        w = csv.writer(fout)
        w.writerow(["time", "frequency", "confidence"])
        for row in csv.DictReader(fin):
            try:
                t, hz, c = float(row["time"]), float(row["frequency"]), float(row["confidence"])
            except (KeyError, ValueError):
                continue
            i = min(int(round(t / HOP_S)), len(active) - 1)
            if not active[i]:
                dropped_silent += 1
            elif c < conf_min or hz <= 50:
                dropped_conf += 1
            else:
                w.writerow([f"{t:.4f}", f"{hz:.4f}", f"{c:.4f}"])
                kept += 1
    return {"method": "voice-stem-loudness", **level, "kept": kept,
            "dropped_silent": dropped_silent, "dropped_low_conf": dropped_conf, "out": str(out_csv)}
