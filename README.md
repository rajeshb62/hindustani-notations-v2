# Hindustani notations

A fresh transcription + listening app. Goal: sargam that is accurate enough that switching from the recording to the notes at any moment still feels like the same performance.

The older Claude Code app baked **labels** at a pinned Sa. If Sa or a CREPE octave hop was wrong, the player could only replay the mistake. This app stores **measured pitch (Hz)** and derives swaras from Sa, so you can retune shruti in the player and the notation remaps.

## Why a new app

Accuracy is the product. Noise, tanpura/tabla, and a wrong Sa destroy the experience even if 90% of frames are close.

| Failure in the old path | What this app does instead |
|---|---|
| Labels frozen at one Sa | Notation is Hz-first; Sa is evidence + a live tuner |
| 12 equal 100-cent steps | Just-intonation ratios, same ones the synth plays |
| Score loop vs CREPE (circular) | Confidence = tracker confidence × distance-to-swara × optional dual-tracker agreement |
| One f0 source | CREPE if present, else pYIN; both if both exist |
| Tanpura bleed as “notes” | Sa taken first from accompaniment; those harmonics are rejected in the vocal track |
| No way to see a bad snap | Player shows cents off the ideal swara and dims low-confidence notes |

Listening is still the judge. This architecture makes a wrong Sa or a shaky frame *visible and fixable* instead of baked in.

## Listen

```bash
cd "/Users/rajeshbhat/grok/hindustani notations/player"
python3 serve.py
# then open http://127.0.0.1:8765/  (ICCR Side B loads automatically)
```

Use `serve.py`, not `python3 -m http.server`. Chrome will not scrub or rewind unless the server answers byte **Range** requests (`206 Partial Content`). Plain `http.server` ignores Range, Chrome’s `currentTime` seek fails, and the timer snaps back to `0:00`.

Open http://127.0.0.1:8765/

Space play/pause · **N** notes/recording. Sa is fixed from the transcription (no on-screen tuner).

## Loop transcribed notes (standalone)

Same server, different page. Plays ICCR Side B or Jasraj Side A as an 8-beat looping stream (quantized like the Claude Code melody generator, but from the transcription, not random):

http://127.0.0.1:8765/loop.html

## Transcribe a new recording

```bash
cd "/Users/rajeshbhat/grok/hindustani notations"
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python3 -m pipeline.run path/to/performance.mp3 --title "Performance title"
```

That writes `data/<slug>/performance.json` and copies/links audio for the player.

Options:

- `--sa 96.97` pin Sa if you already know it
- `--skip-demucs` if you already have a vocal wav
- `--f0-csv path.csv` reuse an existing CREPE/pYIN file (`time,frequency,confidence`)

## Layout

```text
pipeline/     isolate → Sa → f0 → VAD → transcribe
player/       listen-along UI
data/         per-performance audio + performance.json
```
