"""Listener corrections: what a listener heard, applied to the transcription.

data/<slug>/corrections.json is curated by hand from that recording's
feedback.json (only entries that clearly say what is there):

- no_voice: ranges with no singer (sarangi/harmonium/tanpura only). Pitch
  frames there are dropped before notes are formed, so neither notes nor the
  pitch curve play. Automatic detection of these was tried and parked: timbre
  embeddings and accompaniment-overlap both flagged soft singing under loud
  accompaniment as "no voice".
- drop_notes: specific notes the listener heard as not the singer's (e.g. a
  Sa' between Pa's that coincides with a tabla stroke). Removed after
  transcription and audited in removed_notes with reason "listener".
"""

from __future__ import annotations

import json
from pathlib import Path


def load(perf_dir: Path) -> dict:
    p = perf_dir / "corrections.json"
    return json.loads(p.read_text()) if p.exists() else {"no_voice": [], "drop_notes": []}


def drop_no_voice(frames: list, corr: dict) -> list:
    spans = [(c["start"], c["end"]) for c in corr.get("no_voice", [])]
    return [f for f in frames if not any(a <= f.t < b for a, b in spans)]


def flag_listener_notes(notes: list, corr: dict) -> list:
    for c in corr.get("drop_notes", []):
        for n in notes:
            if c["start"] <= n.t < c["end"] and n.label in c["labels"] and n.flag is None:
                n.flag = "listener"
    return notes
