# Hindustani notations

A fresh transcription + listening app. Goal: sargam that is accurate enough that switching from the recording to the notes at any moment still feels like the same performance.

The older Claude Code app baked **labels** at a pinned Sa. If Sa or a CREPE octave hop was wrong, the player could only replay the mistake. This app stores **measured pitch (Hz)** and derives swaras from Sa, so a wrong Sa is fixed by re-pinning it (`pipeline.retranscribe --sa`) without re-running Demucs or pitch tracking.

## Why a new app

Accuracy is the product. Noise, tanpura/tabla, and a wrong Sa destroy the experience even if 90% of frames are close.

| Failure in the old path | What this app does instead |
|---|---|
| Labels frozen at one Sa | Notation is Hz-first; Sa comes from tanpura + vocal evidence and can be re-pinned |
| 12 equal 100-cent steps | Swara positions measured per performance (just table as the fallback); the synth plays the same positions |
| Score loop vs CREPE (circular) | Confidence = tracker confidence × distance-to-swara |
| One f0 source | CREPE if installed, else pYIN (both are saved; only one is used so far) |
| Tanpura bleed as “notes” | Sa taken first from accompaniment; Sa/Pa pitches heard *outside* vocal segments are dropped (sung Sa/Pa are kept) |
| No way to see a bad snap | Player shows cents off the ideal swara and dims low-confidence notes |
| Quantized notes lose meend/gamak | Player can also play the measured pitch curve itself |

Listening is still the judge. This architecture makes a wrong Sa or a shaky frame *visible and fixable* instead of baked in.

## Recordings

Audio is not in git. All recordings are from the Internet Archive's NCPA collection; fetch them (checked by size) into `data/` before listening:

```bash
python3 -m pipeline.fetch_audio
```

| Performance | Internet Archive item | Side |
|---|---|---|
| Chhayanat — Pandit Raja Kale (Sa ≈ 172 Hz; the tape's Shuddh Kalyan is on side A) | [ICCR-1854-AC](https://archive.org/details/dni.ncaa.ICCR-1854-AC) | B |
| Pandit Jasraj — Jaunpuri for the first ~15 min; the rest not identified (both Ni, no Dha) | [SF-SFC000755-AC](https://archive.org/details/dni.ncaa.SF-SFC000755-AC) | A |
| Pandit Jasraj — Gujari Todi for the first ~15 min (Todi without Pa; Ma-tuned tanpura); the rest not identified (mixed Ga/Dha, then near Asavari) | [SF-SFC000755-AC](https://archive.org/details/dni.ncaa.SF-SFC000755-AC) | B |
| Todi — D. V. Paluskar | [SKSS-T206-AC](https://archive.org/details/dni.ncaa.SKSS-T206-AC) (Bandishes in Raga Todi, Vol. I) | A |
| Todi — Ghulam Ali | [SKSS-T206-AC](https://archive.org/details/dni.ncaa.SKSS-T206-AC) | B |
| Todi — Vidushi Ashwini Bhide Deshpande | [SKSS-T208-AC](https://archive.org/details/dni.ncaa.SKSS-T208-AC) (Bandishes in Raga Todi, Vol. III) | A |

## Listen

```bash
cd player
python3 serve.py
# then open http://127.0.0.1:8765/  (ICCR Side B loads automatically)
```

Use `serve.py`, not `python3 -m http.server`. Chrome will not scrub or rewind unless the server answers byte **Range** requests (`206 Partial Content`). Plain `http.server` ignores Range, Chrome’s `currentTime` seek fails, and the timer snaps back to `0:00`.

Open http://127.0.0.1:8765/

Space play/pause · **N** cycles what you hear: **Recording → Notes** (each note at its ideal just-intonation pitch) **→ Pitch curve** (the measured f0, so glides and ornaments stay intact). Notes are scheduled on the Web Audio clock and glide into short notes, so fast passages don't click. Sa is fixed from the transcription.

## Loop transcribed notes (standalone)

Same server, different page. Plays ICCR Side B or Jasraj Side A as an 8-beat looping stream (quantized like the Claude Code melody generator, but from the transcription, not random):

http://127.0.0.1:8765/loop.html

## Transcribe a new recording

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python3 -m pipeline.run path/to/performance.mp3 --title "Performance title"
```

That writes `data/<slug>/performance.json` and copies/links audio for the player.

Options:

- `--sa 96.97` pin Sa if you already know it
- `--skip-demucs` if you already have a vocal wav
- `--f0-csv path.csv` reuse an existing CREPE/pYIN file (`time,frequency,confidence`)
- `--raga todi` (or any of the 16 in `pipeline/raga.py`) choose Sa as the tanpura peak — read as Sa, Pa or Ma, any octave — that puts the singing on the raga's swaras, and report how much held singing is on them (`raga_check`). Paluskar's Todi: the strongest tanpura peak was Pa; the raga fit picked Sa at 161.5 Hz (92% vs 44%).

CREPE is not installed in this venv. For long recordings run the chunked, resumable tracker under any Python that has `crepe` (TensorFlow-based; separate from this venv), then pass its CSV with `--f0-csv`:

```bash
/path/to/venv-with-crepe/bin/python \
    pipeline/crepe_chunked.py data/<slug>/work/vocals.wav data/<slug>/work/f0_crepe.csv
```

Demucs falls back to CPU when the Mac GPU (MPS) rejects a long track.

## Re-transcribe without re-tracking

Changing the note grouping, or re-pinning Sa, only needs the saved `work/f0.vad.csv`:

```bash
python3 -m pipeline.retranscribe                          # all performances
python3 -m pipeline.retranscribe iccr-1854-side-b --sa 97.2
```

Grouping follows the by-ear known-good settings: join same-swara frames across gaps up to 75 ms, never across octaves; absorb sub-20 ms flickers inside a held note (A–x–A → A); then drop anything still under 20 ms. Two-frame kan swaras survive.

Notes that are not something the singer sang are **removed from the transcription** (listed with the reason in `performance.json` → `removed_notes`): `range` — more than 5 semitones outside the singer's own range (time-weighted 1st–99th percentile), i.e. instrument bleed or the tracker jumping to the voice's 2nd harmonic (Jasraj side A 25:33, where a held S' flips to S'' at exactly 2×); `octave` — short notes flickering exactly an octave from their neighbour (Jasraj 21:46). The pitch curve drops those frames too. Every other note, including fast ornaments and glide fragments, is kept.

## Per-performance tuning (`pipeline/calibrate.py`)

Intonation depends on raga and singer, so each performance gets its own swara positions:

1. **Sa** is refined by the median offset of held Sa and Pa notes (the fixed reference swaras). Always re-derived from the original pin, so re-running is stable.
2. **Other swaras** move to the median of their held (≥150 ms), trusted notes, clamped to ±30¢ of the just table; swaras with fewer than 8 held notes keep the table value.
3. Everything is relabelled against those positions. They are stored in `performance.json` (`swara_positions`, `calibration`) and used by both players.

Checked against sargam sung by the singer (Jasraj side A 0:00–0:39): the pinned Sa was ~8¢ low, komal Ga/Dha sit ~14/12¢ above the table, and the transcription agrees with 39 of 43 sung syllables matched to held pitches. `--no-calibrate` reverts to the pinned Sa and the just table.

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
