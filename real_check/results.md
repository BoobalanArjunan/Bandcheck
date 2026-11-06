# bandcheck real-data check

Files used: 200 from `/Users/mymac/LibriSpeech/dev-clean`

## 1. The files as they are

PASS 185, WARN 11, FAIL 1, REVIEW 3, ERROR 0

| sample rate | files | flagged (WARN or FAIL) | median cut-off |
|---|---|---|---|
| 16000 Hz | 200 | 12 | 7.0 kHz |

First flagged files (open a few in a spectrogram viewer and check by eye):

- WARN 2086-149220-0009.flac: sound stops at 7.1 kHz (89% of the way to 8 kHz)
- WARN 3170-137482-0019.flac: sound stops at 7.1 kHz (88% of the way to 8 kHz)
- WARN 777-126732-0044.flac: sound stops at 7.0 kHz (88% of the way to 8 kHz)
- WARN 3170-137482-0006.flac: sound stops at 7.1 kHz (89% of the way to 8 kHz)
- WARN 777-126732-0069.flac: sound stops at 7.0 kHz (88% of the way to 8 kHz)
- WARN 777-126732-0029.flac: sound stops at 7.0 kHz (88% of the way to 8 kHz)
- WARN 2086-149214-0000.flac: sound stops at 7.0 kHz (88% of the way to 8 kHz)
- WARN 2086-149220-0007.flac: sound stops at 7.1 kHz (88% of the way to 8 kHz)
- WARN 3170-137482-0035.flac: sound stops at 7.0 kHz (87% of the way to 8 kHz)
- FAIL 7850-286674-0017.flac: sound stops at 4.8 kHz, only 59% of the way to 8 kHz
- WARN 777-126732-0028.flac: sound stops at 7.0 kHz (88% of the way to 8 kHz)
- WARN 2086-149220-0016.flac: sound stops at 7.1 kHz (89% of the way to 8 kHz)

## 2. Planted upsampling (known true bandwidth)

| copy | files tried | flagged (WARN/FAIL) | FAIL | median cut-off / true bandwidth |
|---|---|---|---|---|
| from 8000 Hz | 185 | 185 | 185 | 1.03 |
| from 11025 Hz | 185 | 185 | 0 | 1.05 |
| from 16000 Hz | 0 | 0 | 0 | n/a |

The last column is 1.00 when the cut-off sits exactly at the source's Nyquist frequency; resampler filters put it a little above.
