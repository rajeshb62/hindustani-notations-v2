"""Pitch track: CREPE when installed, otherwise librosa pYIN. Optional agreement."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np


def _write_csv(path: Path, times: np.ndarray, freqs: np.ndarray, conf: np.ndarray) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "frequency", "confidence"])
        for t, hz, c in zip(times, freqs, conf):
            if not np.isfinite(hz) or hz <= 0:
                w.writerow([f"{t:.4f}", 0.0, 0.0])
            else:
                w.writerow([f"{t:.4f}", f"{hz:.4f}", f"{float(c):.4f}"])


def extract_pyin(wav_path: Path, out_csv: Path, sr: int = 16000, hop: int = 160) -> Path:
    import librosa

    y, file_sr = librosa.load(wav_path, sr=sr, mono=True)
    f0, voiced_flag, voiced_prob = librosa.pyin(
        y,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C6"),
        sr=file_sr,
        hop_length=hop,
        fill_na=0.0,
    )
    times = librosa.times_like(f0, sr=file_sr, hop_length=hop)
    conf = np.where(voiced_flag, np.clip(voiced_prob, 0, 1), 0.0)
    conf = np.nan_to_num(conf, nan=0.0)
    _write_csv(out_csv, times, np.nan_to_num(f0, nan=0.0), conf)
    return out_csv


def extract_crepe(wav_path: Path, out_csv: Path) -> Path:
    import crepe
    import librosa

    y, sr = librosa.load(wav_path, sr=16000, mono=True)
    time, frequency, confidence, _ = crepe.predict(
        y, sr, model_capacity="full", viterbi=True, step_size=10, verbose=0
    )
    _write_csv(out_csv, time, frequency, confidence)
    return out_csv


def extract_f0(wav_path: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    used = []
    crepe_csv = out_dir / "f0_crepe.csv"
    pyin_csv = out_dir / "f0_pyin.csv"
    try:
        extract_crepe(wav_path, crepe_csv)
        used.append("crepe")
    except Exception as exc:
        crepe_csv = None
        crepe_err = str(exc)
    else:
        crepe_err = None
    extract_pyin(wav_path, pyin_csv)
    used.append("pyin")

    primary = crepe_csv if crepe_csv and crepe_csv.exists() else pyin_csv
    return {
        "primary_csv": str(primary),
        "crepe_csv": None if crepe_csv is None else str(crepe_csv),
        "pyin_csv": str(pyin_csv),
        "trackers": used,
        "crepe_error": crepe_err,
    }
