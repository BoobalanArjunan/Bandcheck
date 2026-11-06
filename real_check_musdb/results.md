# bandcheck real-data check

Files used: 200 from `/Users/mymac/Desktop/Beatunzip-Test/musdb18hq/test`

## 1. The files as they are

PASS 197, WARN 2, FAIL 0, REVIEW 1, ERROR 0

| sample rate | files | flagged (WARN or FAIL) | median cut-off |
|---|---|---|---|
| 44100 Hz | 200 | 2 | 21.4 kHz |

First flagged files (open a few in a spectrogram viewer and check by eye):

- WARN other.wav: sound stops at 19.1 kHz (87% of the way to 22.05 kHz)
- WARN drums.wav: sound stops at 19.3 kHz (87% of the way to 22.05 kHz)

## 2. Planted upsampling (known true bandwidth)

| copy | files tried | flagged (WARN/FAIL) | FAIL | median cut-off / true bandwidth |
|---|---|---|---|---|
| from 8000 Hz | 197 | 191 | 191 | 1.02 |
| from 11025 Hz | 197 | 185 | 185 | 1.05 |
| from 16000 Hz | 197 | 162 | 162 | 1.10 |

The last column is 1.00 when the cut-off sits exactly at the source's Nyquist frequency; resampler filters put it a little above.

## 3. MP3 copies (cut-off found; the true lowpass depends on the encoder)

| bitrate | files tried | flagged (WARN/FAIL) | median cut-off |
|---|---|---|---|
| 64 kbps | 197 | 171 | 11.1 kHz |
| 128 kbps | 197 | 157 | 16.5 kHz |
