# RoughCut

A local macOS CLI that turns a folder of raw footage into a clean rough cut
you drop into DaVinci Resolve. It only removes the boring/dead material —
silence, filler words, repeated takes, and (optionally) overly long static
b-roll shots — and hands off a cut list. All creative decisions (pacing,
music, color, final polish) stay in Resolve.

**Non-goals:** no full auto-edit, no music/transitions/color/render. Source
media is never modified, moved, or re-encoded — cuts are frame-accurate
references into the originals.

## How it decides what to cut

Every clip is transcribed locally (faster-whisper, word-level timestamps),
then run through independent detectors:

| Detector | What it flags | Action |
|---|---|---|
| Silence | dead-air gaps longer than a threshold | cut, with a padding guard-band so word onsets/offsets are never clipped |
| Filler words | um/uh/like/you know/etc. from the transcript | cut if the ASR was confident it heard the word, otherwise flagged for review |
| Duplicate takes | near-identical sentences repeated in the same clip (false starts / re-recordings) | earlier takes cut if similarity is high, the **last** take is always kept |
| Long shots | static b-roll shots longer than a max length (PySceneDetect) | **always flagged, never auto-cut** — just a suggestion to trim manually in Resolve |

A clip is classified as **talking-head** (gets filler-word + duplicate-take
detection) or **b-roll** (gets long-shot detection) automatically, based on
what fraction of its duration has transcribed speech — no manual sorting
into folders required. Silence detection runs on every clip either way.

**Low-confidence decisions are never silently removed.** Anything below the
cut-confidence threshold is kept in the rough cut but flagged: it shows up
in `cut_report.md` under "Needs Review" *and* as a yellow marker at that
point on the FCPXML timeline, so it's visible right on the clip in Resolve.
Pass `--conservative` to raise every threshold at once and bias toward
flagging over cutting.

## Setup

```bash
# 1. ffmpeg (proxy render + audio extraction only — never used to touch source media)
brew install ffmpeg

# 2. Python env
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

The first run of `roughcut process` downloads the faster-whisper model
(`small` by default, ~500MB) from Hugging Face and caches it under
`~/.cache/huggingface` — after that it's fully offline.

## Usage

```bash
roughcut process /path/to/footage/folder --output ./output
```

Produces in `./output`:

- `rough_cut.fcpxml` — import into DaVinci Resolve (File → Import → Timeline).
  References the original media files at their original paths/timecodes —
  relink to the originals in Resolve for full quality, no re-encoding.
- `rough_cut.edl` — CMX3600 EDL fallback, for tools that don't read FCPXML
  (note: EDL has no concept of full file paths, only reel names, so it's
  strictly a fallback to the FCPXML).
- `rough_cut_proxy.mp4` — low-res concatenation of the kept ranges, for a
  quick sanity-check scrub before opening Resolve.
- `cut_report.md` — every cut, why, with timestamps, plus a "Needs Review"
  section for anything flagged instead of auto-cut.

### Overriding thresholds

Either flags:

```bash
roughcut process ./footage --output ./output \
  --min-silence-duration 0.5 \
  --max-shot-length 6 \
  --duplicate-similarity-threshold 0.85 \
  --filler-words "um,uh,like,you know,so yeah" \
  --whisper-model medium \
  --conservative
```

...or a config file (`roughcut process ./footage --config myconfig.toml`):

```toml
min_silence_duration = 0.5
max_shot_length = 6.0
duplicate_similarity_threshold = 0.85
filler_words = ["um", "uh", "like", "you know"]
whisper_model = "medium"
conservative = false
```

CLI flags take precedence over the config file, which takes precedence over
built-in defaults. See `roughcut/config.py` for the full list of tunable
fields (silence, filler, duplicate-take, scene-detection, classification,
whisper, and proxy-render settings).

### Clip ordering

Clips are assembled in sorted file-path order (folder is scanned
recursively). Name your source files so alphabetical order matches shooting
order (most camera auto-naming already does this).

## Known limitations

- **FCPXML adapter scope**: `rough_cut.fcpxml` is generated via the
  community-maintained `otio-fcpx-xml-adapter`, which explicitly doesn't
  implement the full FCPXML spec (no transitions/effects — irrelevant here
  since RoughCut doesn't add any). It also emits some inert, unreferenced
  `<asset-clip>` resource declarations alongside the real timeline `<spine>`;
  these don't affect the actual cut list but are a known quirk of this
  adapter. **Always test-import the first FCPXML from a new setup into
  Resolve and confirm clips + audio look right before archiving anything.**
- **Proxy timing**: `rough_cut_proxy.mp4` is a disposable low-res preview —
  its concatenation can drift by a couple hundred milliseconds across many
  short segments. `rough_cut.fcpxml` is the frame-accurate source of truth.
  (Portrait and landscape source clips are automatically padded to a common
  resolution so mixed-orientation footage concatenates safely.)
- **Scene detection** (PySceneDetect) needs actual visual content changes;
  it won't fire correctly on completely static test patterns without scene
  cuts, and its threshold may need tuning per camera/lighting setup.
- **Corrupt/unreadable source files** are skipped (with a warning and a
  "Skipped files" section in the report) rather than aborting the whole run.
- **Mixed frame rates across source clips**: the FCPXML handles this
  correctly per-clip, but the EDL fallback is a single-project-rate format by
  nature — it uses the first clip's fps for the whole timeline, so clips shot
  at a different rate will have incorrect EDL timecodes (a warning is logged
  when this happens). Treat the FCPXML as authoritative in mixed-rate folders.
- **Duplicate-take detection is per-clip only**, matching the "repeated takes
  within a clip" scope — if you start a new source file per take, RoughCut
  won't compare across separate files.

## Sample/test footage

`samples/generate_samples.sh` synthesizes a couple of short local test
clips (macOS `say` for speech + `ffmpeg` lavfi color sources — no external
media) covering silence gaps, a filler word, a repeated false-start take,
and long static b-roll shots:

```bash
./samples/generate_samples.sh          # writes samples/raw/*.mp4
roughcut process samples/raw --output samples/output
cat samples/output/cut_report.md
```

## Tests

```bash
pip install -e ".[dev]"
pytest tests/
```

Unit tests cover the detector/assembly logic directly (no real media
needed); the sample flow above is the end-to-end check.

## Project layout

```
roughcut/
  models.py         clip + transcript + keep/cut/review data model
  config.py         defaults + config file/CLI override merging
  media.py          ffprobe/ffmpeg helpers (probe, audio extraction)
  transcription.py  faster-whisper wrapper, word-level timestamps + confidence
  classify.py       talking-head vs b-roll classification
  silence.py        WebRTC VAD dead-air detection + guard-band padding
  fillers.py        filler-word matching with confidence-gated cut/review
  duplicates.py     duplicate/false-start take detection (keeps last take)
  scenes.py         PySceneDetect long-shot flagging (b-roll, flag-only)
  assembly.py       merges all detector decisions into KEEP/CUT/REVIEW ranges
  export.py         builds the OTIO timeline, exports FCPXML + EDL
  proxy.py          ffmpeg low-res preview render
  report.py         markdown cut report
  pipeline.py       orchestrates the full run
  cli.py            `roughcut process ...`
```
