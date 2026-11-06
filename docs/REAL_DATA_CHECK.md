# Real-data check (do this before trusting bandcheck)

bandcheck has only been tested on **generated audio with a known bandwidth**. Real recordings have room noise, gentle
filters, odd mastering and files that were band-limited long before you got them. Nothing about real-data accuracy is
claimed until this check is run.

## What you need
A folder of real audio files. Check the licence of any dataset before using it. Good choices:
- LibriSpeech (16 kHz speech). It was made from MP3 audiobooks, so some files may be truly band-limited: a useful test.
- Your own music or speech files, ideally at 44.1 or 48 kHz.

## Run it
```bash
pip install -e ".[dev]"
python scripts/real_data_check.py --audio-dir ~/LibriSpeech/dev-clean --out real_check
python scripts/real_data_check.py --audio-dir ~/music --out real_check --mp3      # optional, needs ffmpeg
```
Send me `real_check/results.md`. It has three parts:
1. **The files as they are.** How many PASS, WARN, FAIL and REVIEW, and the cut-off per sample rate. Open a few flagged files
   in a spectrogram viewer (for example Audacity: Spectrogram view) and say whether the flag is right.
2. **Planted upsampling.** Copies made from 8, 11.025 and 16 kHz versions of files that passed. The real bandwidth is known, so
   this shows how many BandCheck catches and how close its cut-off is.
3. **MP3 copies** (with `--mp3`): the cut-offs it finds at 64 and 128 kbps.

Your original files are never modified. Copies go under `real_check/planted/`.

## How I will use the numbers
The defaults in `src/bandcheck/spectrum.py` and `check.py` (a 25 dB drop counts as a cut-off, 90% of Nyquist or 19.5 kHz
is "full band", under 60% is a failure) were set on generated audio. They will be adjusted from your results, and the
README will quote what was measured.
