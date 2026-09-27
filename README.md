# Hindustani notations

A fresh transcription + listening app. Goal: sargam that is accurate enough that switching from the recording to the notes at any moment still feels like the same performance.

The older Claude Code app baked **labels** at a pinned Sa. If Sa or a CREPE octave hop was wrong, the player could only replay the mistake. This app stores **measured pitch (Hz)** and derives swaras from Sa, so a wrong Sa is fixed by re-pinning it (`pipeline.retranscribe --sa`) without re-running Demucs or pitch tracking.

## Why a new app

Accuracy is the product. Noise, tanpura/tabla, and a wrong Sa destroy the experience even if 90% of frames are close.

| Failure in the old path | What this app does instead |
|---|---|
| Labels frozen at one Sa | Notation is Hz-first; Sa comes from tanpura + vocal evidence and can be re-pinned |
| 12 equal 100-cent steps | Just-intonation ratios, same ones the synth plays |
| Score loop vs CREPE (circular) | Confidence = tracker confidence × distance-to-swara |
| One f0 source | CREPE if installed, else pYIN (both are saved; only one is used so far) |
| Tanpura bleed as “notes” | Sa taken first from accompaniment; Sa/Pa pitches heard *outside* vocal segments are dropped (sung Sa/Pa are kept) |
| No way to see a bad snap | Player shows cents off the ideal swara and dims low-confidence notes |
| Quantized notes lose meend/gamak | Player can also play the measured pitch curve itself |

Listening is still the judge. This architecture makes a wrong Sa or a shaky frame *visible and fixable* instead of baked in.

## Listen

```bash
cd "/Users/rajeshbhat/grok/hindustani notations/player"
python3 serve.py
# then open http://127.0.0.1:8765/  (ICCR Side B loads automatically)
```

Use `serve.py`, not `python3 -m http.server`. Chrome will not scrub or rewind unless the server answers byte **Range** requests (`206 Partial Content`). Plain `http.server` ignores Range, Chrome’s `currentTime` seek fails, and the timer snaps back to `0:00`.

Open http://127.0.0.1:8765/

Space play/pause · **N** cycles what you hear: **Recording → Notes** (each note at its ideal just-intonation pitch) **→ Pitch curve** (the measured f0, so glides and ornaments stay intact). **S** toggles detailed (default) / strict (suspect short notes hidden). Out-of-range notes are hidden in both. Notes are scheduled on the Web Audio clock and glide into short notes, so fast passages don't click. Sa is fixed from the transcription.

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

## Re-transcribe without re-tracking

Changing the note grouping, or re-pinning Sa, only needs the saved `work/f0.vad.csv`:

```bash
python3 -m pipeline.retranscribe                          # all performances
python3 -m pipeline.retranscribe iccr-1854-side-b --sa 97.2
```

Grouping follows the by-ear known-good settings: join same-swara frames across gaps up to 75 ms, never across octaves; absorb sub-20 ms flickers inside a held note (A–x–A → A); then drop anything still under 20 ms. Two-frame kan swaras survive.

Correctness before granularity: short notes (< 80 ms) are **flagged** when they are probably glide fragments rather than swaras the singer landed on — more than 25¢ off the swara (`offcentre`), or lying between their neighbours' pitches inside a meend (`passing`). A kan that turns above or below both neighbours is kept. Notes of any length are flagged `range` when they fall more than 5 semitones outside the singer's own range (time-weighted 1st–99th percentile): instrument bleed or the tracker jumping to the voice's 2nd harmonic, e.g. Jasraj side A 25:33, where a held S' flips to S'' at exactly 2×. The pitch curve drops those frames too. The player defaults to **detailed** (suspect short notes shown, dimmed); **S** toggles strict, which hides them.

## Tests

```bash
.venv/bin/python -m unittest discover tests
```

## Layout

```text
pipeline/     isolate → Sa → f0 → VAD → transcribe
player/       listen-along UI
tests/        pipeline unit tests
data/         per-performance audio + performance.json
```
