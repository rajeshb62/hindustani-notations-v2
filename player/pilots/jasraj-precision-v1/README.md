# Jasraj precision-first pilot

Open on this Mac: http://127.0.0.1:8765/pilots/jasraj-precision-v1/index.html

Use Recording / Current notes / Conservative candidate at the same position. Select an excerpt and optionally Loop excerpt. Both note versions use the same simple just-intonation sine synth, Sa 136.18 Hz. Recording is the original mix. Their timbre differs from the original app's flute synth; this comparison isolates notation differences.

## Result and limits

23 accepted notes covering 3.81 seconds within 87 analyzed seconds. This is **very sparse**, not a demonstrated improvement. Listen first to 0:05–0:20, 0:30–0:43, and 43:50–44:05. The other three excerpts retain no notes; they remain selectable so omissions are explicit. No coverage outside these windows is implied.

| Excerpt | Current notes overlapping excerpt | Candidate notes |
|---|---:|---:|
| 0:05–0:20 | 73 | 12 |
| 0:30–0:43 | 86 | 7 |
| 11:39–11:53 | 39 | 0 |
| 25:00–25:15 | 4 | 0 |
| 41:30–41:45 | 51 | 0 |
| 43:50–44:05 | 111 | 4 |

Current counts include notes overlapping boundaries. Gaps mean **untranscribed**, not silence in the singing. Historical speech VAD is an imperfect vocal-presence proxy: particularly 11:39 and later passages can be wrongly excluded. Sparse output is not evidence those phrases lack clear sung notes. Do not promote this as a full transcription.

## Real evidence used

- Existing Demucs vocal stem, not a new separation.
- Historical raw CREPE CSV, not just current notation labels or the VAD rescue CSV.
- Fresh RMVPE inference on each padded excerpt (model hash/provenance in rmvpe-provenance.json).
- Fresh pYIN on vocal stem and original mix. Vocal pYIN provides a disagreement veto when its voicing evidence is strong; source-mix pYIN is diagnostic only.
- Historical Silero speech-VAD intervals, with edges trimmed by 500 ms.

The initial mandatory pYIN agreement trial kept seven notes. It is preserved in initial-pyin-report.json. The final candidate instead uses two distinct neural pitch trackers, with pYIN as a conflict veto. This does not turn any tracker score into a probability of being musically correct.

## Conservative rules

Each accepted frame requires historical VAD support, CREPE score >=0.90, RMVPE salience >=0.30, and CREPE/RMVPE absolute-pitch agreement within 30 cents. Confident vocal pYIN (voicing score >=0.50) vetoes disagreements >35 cents. RMVPE pitch must be within 25 cents of the assigned fixed-ratio swara. Runs must be contiguous for at least 100 ms with the same swara AND octave. No gap filling, octave averaging, or blanket drone-harmonic rejection. Note frequency is the median accepted RMVPE frequency; playback renders its labelled ideal swara.

Thresholds are conservative engineering hypotheses, not calibrated correctness guarantees. Both neural trackers may still follow accompaniment. Short notes, ornaments and meend are heavily omitted. No human accuracy assessment has been performed. Your listening decides whether these retained anchors are useful; useful phrase reconstruction is not yet established.

## Reproduce (candidate-only outputs)

Working directory: this folder.

```
'/Users/rajeshbhat/claudecode/hindustani notations/venv/bin/python' analyze.py
'/Users/rajeshbhat/claudecode/hindustani notations/venv/bin/python' corroborate_rmvpe.py
python3 precision.py
python3 verify.py
```

`analyze.py` writes the initial trial; run `precision.py` after it to restore the final candidate. Cached evidence and model provenance are preserved. No current performance JSON, root player, catalog or production deployment was changed. The existing 8765 server serves this pilot; if stopped, run `python3 serve.py` from the project's player directory.
