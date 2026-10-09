# Hindustani notations

A fresh transcription + listening app. Goal: sargam that is accurate enough that switching from the recording to the notes at any moment still feels like the same performance.

The older Claude Code app baked **labels** at a pinned Sa. If Sa or a CREPE octave hop was wrong, the player could only replay the mistake. This app stores **measured pitch (Hz)** and derives swaras from Sa, so a wrong Sa is fixed by re-pinning it (`pipeline.retranscribe --sa`) without re-running voice separation or pitch tracking.

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
| Desh — Shri Kalyan Chattopadhyay (vilambit ektal, drut teentaal) | [ICCR-923-AC](https://archive.org/details/dni.ncaa.ICCR-923-AC) | A |
| ~~Bihag — Ustad Khadim Hussain Khan~~ — hidden: tape noise drowns the singer (`data/<slug>/hidden.json` keeps a recording out of the player) | [SF-SFC001103-AC](https://archive.org/details/dni.ncaa.SF-SFC001103-AC) | A |
| Yaman — Pandit Madhav Umdekar | [SF-SFC000980-AC](https://archive.org/details/dni.ncaa.SF-SFC000980-AC) | A |

## Listen

```bash
cd player
python3 serve.py
# then open http://127.0.0.1:8765/  (ICCR Side B loads automatically)
```

Use `serve.py`, not `python3 -m http.server`. Chrome will not scrub or rewind unless the server answers byte **Range** requests (`206 Partial Content`). Plain `http.server` ignores Range, Chrome’s `currentTime` seek fails, and the timer snaps back to `0:00`.

Open http://127.0.0.1:8765/

Space play/pause · **N** cycles what you hear: **Recording → Notes** (each note at its ideal just-intonation pitch) **→ Pitch curve** (the measured f0, so glides and ornaments stay intact). Notes are scheduled on the Web Audio clock and glide into short notes, so fast passages don't click. Sa is fixed from the transcription.

## Listening feedback

While listening, press **F** to mark the start of a stretch and **F** again to mark its end; playback pauses and a text box opens (⌘/Ctrl+Enter saves, Esc cancels). Feedback is saved by `serve.py` to `data/<slug>/feedback.json` (start, end, text, and which mode you were hearing) and committed with the transcription. Marks show under the scrub bar; **Feedback (n)** in the footer lists them — click one to jump there, ✕ to delete.

To check a stretch: select a feedback (or nothing, for ±4 s around the playhead) and press **L** — once to loop it, again to loop **A/B** (recording and notes alternate each pass), again to stop. The **1×** button slows playback to 0.75× / 0.5× with pitch preserved; notes stay in sync.

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

**Voice separation** uses the MelBand RoFormer "bleedless" model (`audio-separator`, overlap 2; `pipeline/isolate.py`), with htdemucs as a fallback. On listener-labelled Desh stretches htdemucs had it backwards — singing lost to the accompaniment (−74 dB in the voice stem), harmonium leaked into it (−30 dB) — while RoFormer put singing at −25 dB, harmonium at −88 dB and silence at digital silence. Re-running all recordings with it raised agreement with Jasraj's sung sargam from 38/43 to 41/43 and fixed 10 of 12 feedback stretches. About 1.5× real time on Apple GPU. A sarangi (Paluskar 10:49–10:58) is still kept as "voice".

Pitch is then kept only where the voice stem is within 30 dB of its 95th-percentile level (`pipeline/vad_filter.py`).

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

## Listener corrections (`data/<slug>/corrections.json`)

Curated by hand from each recording's listening feedback, only where the feedback clearly says what is there: `no_voice` ranges (sarangi/harmonium/tanpura only — pitch dropped there before notes are formed, so neither notes nor the pitch curve play) and `drop_notes` (a specific note heard as not the singer's, audited in `removed_notes` as `listener`). Applied by `pipeline.run` and `pipeline.retranscribe`. Automatic detection of instrument-only passages was tried and parked: timbre embeddings (PANNs) and accompaniment-pitch overlap both flagged soft singing under loud accompaniment as "no voice" when checked by ear.

## Passing notes (`absorb_passing` in `pipeline/transcribe.py`)

When the raga is known, a short (≤ 120 ms) out-of-raga note the voice only passes through between two neighbouring raga notes is absorbed into them: Yaman 1:44, N → n (30 ms) → D reads N D, as the singer means it. The run's time is split between the neighbours, the note is audited in `removed_notes` as `passing`, and the pitch curve is unchanged. Held out-of-raga notes are left as sung (nearest swara) — whether a held note between two raga notes is a deliberate foreign note or a meend that turns back is a judgement for the ear, not the code. Checked by ear on Yaman 1:44 and Ghulam Ali 5:17. 6–14% of notes per recording, almost all 2–3 frames.

## Where is it weakest? (`pipeline/report.py`)

```bash
python3 -m pipeline.report            # all performances; also writes data/<slug>/report.json
```

Per performance: how much of the time the voice stem is sounding is covered by notes, and the longest uncovered stretches; held notes outside the raga (when known); every listening-feedback entry as a pass/fail check ("no voice" → few notes, "continuous singing" → covered, "Sa'' not in the voice" → no notes two octaves up); and agreement with sung sargam where `sargam_labels.json` exists (Jasraj side A 0:00–0:39, written down by ear by a listener). Coverage needs the local voice stem.

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
