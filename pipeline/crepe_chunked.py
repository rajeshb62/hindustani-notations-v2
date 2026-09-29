#!/usr/bin/env python3
"""CREPE pitch track for long recordings, one chunk at a time.

Standalone (no package imports) so it can run under any Python that has
crepe + tensorflow, e.g. the legacy project's venv:

    /Users/rajeshbhat/claudecode/hindustani\\ notations/venv/bin/python \\
        pipeline/crepe_chunked.py vocals.wav f0_crepe.csv

Full-recording crepe.predict holds every 1024-sample frame in memory at once;
chunks of 60 s with 1 s context on each side keep memory bounded. Viterbi
smoothing runs per chunk; only each chunk's central frames are kept, so the
seams are not visible. Writes time,frequency,confidence (10 ms steps).

If out_csv already has rows (an interrupted run), it resumes at the next
whole chunk after the last written time and appends.
"""

from __future__ import annotations

import csv
import sys
import time

import crepe
import librosa
import numpy as np

SR = 16000
STEP_MS = 10
CHUNK_S = 60.0
PAD_S = 1.0


def _resume_point(out_csv: str) -> float:
    """Start of the first chunk not fully written (chunks start at k*CHUNK_S)."""
    try:
        with open(out_csv) as f:
            rows = list(csv.reader(f))
    except FileNotFoundError:
        return 0.0
    if len(rows) < 2:
        return 0.0
    last = float(rows[-1][0])
    done_chunks = int((last + STEP_MS / 1000 + 1e-6) // CHUNK_S)
    return done_chunks * CHUNK_S


def main(wav: str, out_csv: str) -> None:
    y, _ = librosa.load(wav, sr=SR, mono=True)
    total = len(y) / SR
    t_start = time.time()
    c0 = _resume_point(out_csv)
    if c0 > 0:
        # Drop any partial chunk so it is rewritten whole.
        with open(out_csv) as f:
            rows = list(csv.reader(f))
        keep = [rows[0]] + [r for r in rows[1:] if float(r[0]) < c0 - 1e-6]
        with open(out_csv, "w", newline="") as f:
            csv.writer(f).writerows(keep)
        print(f"resuming at {c0:.0f}s", flush=True)
    start_c0 = c0
    with open(out_csv, "a" if c0 > 0 else "w", newline="") as f:
        w = csv.writer(f)
        if c0 == 0:
            w.writerow(["time", "frequency", "confidence"])
        while c0 < total:
            c1 = min(total, c0 + CHUNK_S)
            a0 = max(0.0, c0 - PAD_S)
            a1 = min(total, c1 + PAD_S)
            seg = y[int(a0 * SR) : int(a1 * SR)]
            t, hz, conf, _ = crepe.predict(
                seg, SR, model_capacity="full", viterbi=True, step_size=STEP_MS, verbose=0
            )
            t = t + a0
            keep = (t >= c0 - 1e-6) & (t < c1 - 1e-6)
            for ti, hi, ci in zip(t[keep], hz[keep], conf[keep]):
                w.writerow([f"{ti:.3f}", f"{hi:.3f}", f"{ci:.6f}"])
            f.flush()
            done = c1 / total
            eta = (time.time() - t_start) / (c1 - start_c0) * (total - c1)
            print(f"crepe {c1:7.1f}/{total:.1f}s  ({100 * done:4.1f}%)  eta {eta / 60:4.1f} min", flush=True)
            c0 = c1
    print("DONE", out_csv, flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
