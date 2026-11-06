import csv

import numpy as np
import pytest
import soundfile as sf
from scipy.signal import firwin, fftconvolve

import bandcheck.check as chk
import synth
from bandcheck.check import (FAKE, LIMITED, OK, UNSURE, check_file, judge, source_guess, summary_by_rate)
from bandcheck.cli import find_audio, main
from bandcheck.report import summary_line, text, write_csv
from bandcheck.spectrum import Cliff, Spectrum, find_cliff, load_mono, mean_spectrum
from conftest import cut, full, up, write


def spec_of(x, sr):
    return mean_spectrum(synth.to_pcm16(x).astype(float) / 32767, sr)


def fake_spec(sr=44100, secs=10.0):
    f = np.linspace(0, sr / 2, 2049)
    return Spectrum(f, np.zeros_like(f), sr, secs, secs)


# ---------------------------------------------------------------- full-band audio passes
@pytest.mark.parametrize("sr", [16000, 22050, 44100, 48000])
def test_full_band_audio_passes(tmp_path, sr):
    v = check_file(write(tmp_path / "a.wav", full(sr), sr))
    assert v.status == OK and v.level == "PASS" and v.cutoff_hz is None
    assert v.sample_rate == sr and v.likely_source == ""


@pytest.mark.parametrize("tilt", [1.0, 1.5, 2.0, 2.5])
def test_steeply_falling_natural_spectra_have_no_cliff(tilt):
    """Dull sound that fades gradually is not a cut-off."""
    assert find_cliff(spec_of(synth.make_full(44100, 12, 1, tilt=tilt), 44100)) is None


def test_quiet_recordings_are_not_flagged(tmp_path):
    for level in (0.001, 0.01):
        assert check_file(write(tmp_path / "q.wav", synth.make_full(44100, 12, 2, level=level), 44100)).status == OK


def test_a_gap_in_the_spectrum_is_not_a_cutoff():
    """A band-stop (sound on both sides) is a notch, not the end of the band."""
    x = full(44100)
    band = firwin(2001, [10000, 11500], pass_zero=False, fs=44100)
    y = x - fftconvolve(x, band, mode="same")
    assert find_cliff(spec_of(y, 44100)) is None


# ---------------------------------------------------------------- lowpass (lossy-encoder-like) detection
@pytest.mark.parametrize("sr,fc", [(44100, 16000), (44100, 19000), (44100, 20000), (48000, 16000), (48000, 20000), (16000, 6000), (16000, 7000)])
def test_cutoff_is_found_where_it_was_put(sr, fc):
    c = find_cliff(spec_of(cut(sr, fc), sr))
    assert c is not None
    assert abs(c.cutoff_hz - fc) / fc < 0.02
    assert c.drop_db > 30 and c.floor_db < -25


def test_cutoff_found_for_other_seeds():
    for seed in (1, 2, 3):
        c = find_cliff(spec_of(cut(44100, 17000, seed), 44100))
        assert c is not None and abs(c.cutoff_hz - 17000) < 400


@pytest.mark.parametrize("sr,fc,status", [
    (44100, 16000, LIMITED), (48000, 16000, LIMITED), (48000, 19000, LIMITED),
    (44100, 20000, OK), (48000, 20000, OK), (16000, 7500, OK), (48000, 10000, FAKE), (44100, 12000, FAKE)])
def test_verdict_for_lowpassed_audio(tmp_path, sr, fc, status):
    v = check_file(write(tmp_path / "a.wav", cut(sr, fc), sr))
    assert v.status == status, v.reason


# ---------------------------------------------------------------- upsampled audio
@pytest.mark.parametrize("sr,src,status", [(16000, 8000, FAKE), (16000, 11025, LIMITED), (44100, 16000, FAKE), (44100, 22050, FAKE),
                                           (48000, 16000, FAKE), (48000, 24000, FAKE), (48000, 8000, FAKE)])
def test_upsampled_audio_is_flagged_and_names_its_source(tmp_path, sr, src, status):
    """Upsampling to a rate close to the source (11.025 to 16 kHz keeps 72% of the band) is a warning; far from it, a failure."""
    v = check_file(write(tmp_path / "a.wav", up(sr, src), sr))
    assert v.status == status, v.reason
    assert 0.9 * src / 2 <= v.cutoff_hz <= 1.12 * src / 2
    assert f"upsampled from {src} Hz" in v.likely_source or f"{src} Hz" in v.likely_source


def test_the_reason_says_how_much_is_missing(tmp_path):
    v = check_file(write(tmp_path / "a.wav", up(48000, 16000), 48000))
    assert "kHz" in v.reason and "% of the way to 24 kHz" in v.reason


def test_source_guess_lists_every_candidate_and_the_lossy_option():
    g = source_guess(5781, 16000)
    assert "11025 Hz" in g and "12000 Hz" in g and "lossy" in g
    assert source_guess(8636, 48000).startswith("upsampled from 16000 Hz")
    assert "upsampled" not in source_guess(3000, 48000) and "lossy" in source_guess(3000, 48000)
    assert "from 48000" not in source_guess(24000, 48000)           # never "upsampled from" the file's own rate or higher
    assert "from 44100" not in source_guess(20000, 44100)


# ---------------------------------------------------------------- need-hz
def test_need_hz_fails_files_that_stop_too_low(tmp_path):
    p = write(tmp_path / "a.wav", cut(44100, 16000), 44100)
    assert check_file(p, need_hz=12000).status == LIMITED
    v = check_file(p, need_hz=18000)
    assert v.status == FAKE and "18 kHz is required" in v.reason


def test_need_hz_does_nothing_without_a_cutoff(tmp_path):
    assert check_file(write(tmp_path / "a.wav", full(44100), 44100), need_hz=20000).status == OK


# ---------------------------------------------------------------- verdict boundaries (cut-off position forced)
def force(monkeypatch, cutoff):
    monkeypatch.setattr(chk, "find_cliff", lambda sp: Cliff(cutoff, 40.0, -40.0))


@pytest.mark.parametrize("sr,cutoff,status", [
    (32000, 0.9 * 16000, OK), (32000, 0.9 * 16000 - 1, LIMITED), (44100, 19500, OK), (48000, 19499, LIMITED),
    (48000, 0.6 * 24000, LIMITED), (48000, 0.6 * 24000 - 1, FAKE), (16000, 0.9 * 8000, OK), (16000, 0.9 * 8000 - 1, LIMITED),
    (16000, 0.6 * 8000 - 1, FAKE)])
def test_thresholds(monkeypatch, sr, cutoff, status):
    force(monkeypatch, cutoff)
    assert judge(fake_spec(sr), "a.wav", sr).status == status


def test_need_hz_boundary(monkeypatch):
    force(monkeypatch, 15000.0)
    assert judge(fake_spec(), "a", 44100, need_hz=15000.0).status == LIMITED
    assert judge(fake_spec(), "a", 44100, need_hz=15000.1).status == FAKE


def test_levels_and_fraction():
    v = chk.Verdict("a", 48000, FAKE, 12000.0, "r")
    assert v.level == "FAIL" and v.fraction == 0.5
    assert chk.Verdict("a", None, chk.ERROR, None, "r").fraction is None
    assert {chk.Verdict("a", 1, s, None, "").level for s in (OK, LIMITED, FAKE, UNSURE, chk.ERROR)} == {"PASS", "WARN", "FAIL", "REVIEW", "ERROR"}


# ---------------------------------------------------------------- edge cases
def test_silent_and_short_files_are_review(tmp_path):
    assert check_file(write(tmp_path / "s.wav", np.zeros(44100 * 10), 44100)).status == UNSURE
    assert check_file(write(tmp_path / "t.wav", full(44100)[:44100], 44100)).status == UNSURE
    assert judge(None, "a", 44100).status == UNSURE


def test_one_click_in_silence_has_too_few_loud_frames(tmp_path):
    x = np.zeros(44100 * 10)
    x[44100] = 0.5
    assert check_file(write(tmp_path / "c.wav", x, 44100)).status == UNSURE


def test_unreadable_file_is_error(tmp_path):
    p = tmp_path / "bad.wav"
    p.write_bytes(b"this is not audio")
    v = check_file(p)
    assert v.status == chk.ERROR and "could not read" in v.reason and v.sample_rate is None


def test_low_sample_rate_without_room_to_search():
    assert judge(spec_of(synth.make_full(8000, 12, 1), 8000), "a", 8000).status == OK


def test_cutoff_below_the_search_start_is_not_reported(tmp_path):
    """A cut-off far below 2.5 kHz is outside the search (speech and music vary a lot there), so it is not flagged."""
    assert find_cliff(spec_of(cut(16000, 1000), 16000)) is None


def test_stereo_equals_mono(tmp_path):
    x = cut(44100, 16000)
    st = np.stack([x, x], axis=1)
    p = tmp_path / "s.wav"
    sf.write(str(p), synth.to_pcm16(st), 44100, subtype="PCM_16")
    a, b = check_file(p), check_file(write(tmp_path / "m.wav", x, 44100))
    assert a.status == b.status and abs(a.cutoff_hz - b.cutoff_hz) < 1.0


def test_one_dead_channel_still_measured(tmp_path):
    x = cut(44100, 16000)
    p = tmp_path / "d.wav"
    sf.write(str(p), synth.to_pcm16(np.stack([x, 0 * x], axis=1)), 44100, subtype="PCM_16")
    assert check_file(p).status == LIMITED


def test_flac_and_24_bit(tmp_path):
    x = cut(48000, 16000)
    sf.write(str(tmp_path / "a.flac"), x, 48000, subtype="PCM_24")
    assert check_file(tmp_path / "a.flac").status == LIMITED


def test_gain_does_not_change_the_result():
    for g in (0.05, 1.0, 3.0):
        c = find_cliff(mean_spectrum(g * cut(44100, 16000), 44100))
        assert c is not None and abs(c.cutoff_hz - 16000) < 400


def test_load_mono_keeps_the_files_own_rate_and_uses_the_middle(tmp_path):
    p = write(tmp_path / "a.wav", full(22050), 22050)
    x, sr = load_mono(p)
    assert sr == 22050 and len(x) == 12 * 22050
    x2, _ = load_mono(p, max_seconds=4)
    assert len(x2) == 4 * 22050


def test_active_seconds_counts_only_loud_parts():
    x = np.concatenate([full(44100)[:44100 * 4], np.zeros(44100 * 8)])
    sp = mean_spectrum(x, 44100)
    assert sp is not None and sp.seconds == pytest.approx(12.0, abs=0.01) and 3.0 < sp.active_seconds < 5.5


def test_quiet_sections_do_not_hide_the_cutoff():
    quiet = 0.001 * full(44100)
    loud = cut(44100, 16000)
    x = np.concatenate([quiet[:44100 * 6], loud[:44100 * 6]])
    c = find_cliff(mean_spectrum(x, 44100))
    assert c is not None and abs(c.cutoff_hz - 16000) < 400


def test_two_cutoffs_the_sharpest_drop_wins():
    x = cut(48000, 20000)
    y = cut(48000, 10000)
    c = find_cliff(spec_of(0.5 * x + 0.5 * y, 48000))
    assert c is not None and (abs(c.cutoff_hz - 10000) < 500 or abs(c.cutoff_hz - 20000) < 500)


# ---------------------------------------------------------------- summary and reports
def test_summary_by_rate():
    vs = [chk.Verdict("a", 48000, FAKE, 8000.0, ""), chk.Verdict("b", 48000, OK, None, ""), chk.Verdict("c", 48000, LIMITED, 16000.0, ""),
          chk.Verdict("d", 16000, OK, None, ""), chk.Verdict("e", None, chk.ERROR, None, "")]
    rows = summary_by_rate(vs)
    assert rows == [{"rate": 16000, "files": 1, "flagged": 0, "median_cutoff_hz": None},
                    {"rate": 48000, "files": 3, "flagged": 2, "median_cutoff_hz": 12000.0}]


def test_text_report_hides_passes_by_default():
    vs = [chk.Verdict("good.wav", 48000, OK, None, "no sharp cut-off found"), chk.Verdict("bad.wav", 48000, FAKE, 8000.0, "stops low", "upsampled from 16000 Hz")]
    t = text(vs)
    assert "bad.wav" in t and "good.wav" not in t and "likely: upsampled from 16000 Hz" in t
    assert "good.wav" in text(vs, show_pass=True)
    assert "48000 Hz: 2 files, 1 flagged" in t
    assert "2 files: 1 pass, 0 warn" in summary_line(vs)


def test_csv_columns_and_values(tmp_path):
    out = tmp_path / "v.csv"
    write_csv(out, [chk.Verdict("a.wav", 48000, FAKE, 8000.0, "r", "x", 9.96)])
    row = list(csv.DictReader(open(out, encoding="utf-8")))[0]
    assert list(row) == ["file", "sample_rate", "cutoff_hz", "cutoff_fraction", "verdict", "reason", "likely_source", "seconds_analysed"]
    assert (row["verdict"], row["cutoff_hz"], row["cutoff_fraction"], row["seconds_analysed"]) == ("FAIL", "8000.0", "0.333", "10.0")


# ---------------------------------------------------------------- command line
def make_folder(tmp_path):
    write(tmp_path / "good.wav", full(44100), 44100)
    write(tmp_path / "limited.wav", cut(44100, 16000), 44100)
    (tmp_path / "sub").mkdir()
    write(tmp_path / "sub" / "fake.wav", up(48000, 16000), 48000)
    return tmp_path


def test_cli_folder_exit_code_and_output(tmp_path, capsys):
    rc = main(["check", str(make_folder(tmp_path))])
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL   fake.wav" in out and "WARN   limited.wav" in out and "good.wav" not in out
    assert "3 files: 1 pass, 1 warn" in out and "By sample rate:" in out


def test_cli_exit_zero_when_nothing_fails(tmp_path, capsys):
    write(tmp_path / "good.wav", full(44100), 44100)
    write(tmp_path / "limited.wav", cut(44100, 16000), 44100)
    assert main(["check", str(tmp_path)]) == 0


def test_cli_single_file_show_pass_and_out(tmp_path, capsys):
    p = write(tmp_path / "good.wav", full(16000), 16000)
    o = tmp_path / "v.csv"
    assert main(["check", str(p), "--show-pass", "--out", str(o)]) == 0
    assert "good.wav" in capsys.readouterr().out
    assert list(csv.DictReader(open(o, encoding="utf-8")))[0]["verdict"] == "PASS"


def test_cli_need_hz(tmp_path, capsys):
    write(tmp_path / "limited.wav", cut(44100, 16000), 44100)
    assert main(["check", str(tmp_path)]) == 0
    assert main(["check", str(tmp_path), "--need-hz", "18000"]) == 1


def test_cli_parallel_jobs_same_result(tmp_path, capsys):
    d = make_folder(tmp_path)
    main(["check", str(d)])
    one = capsys.readouterr().out
    main(["check", str(d), "--jobs", "2"])
    assert capsys.readouterr().out == one


def test_cli_skips_macos_junk_and_non_audio(tmp_path):
    write(tmp_path / "a.wav", full(16000), 16000)
    (tmp_path / "._a.wav").write_bytes(b"junk")
    (tmp_path / "notes.txt").write_text("x")
    (tmp_path / "__MACOSX").mkdir()
    (tmp_path / "__MACOSX" / "b.wav").write_bytes(b"junk")
    assert [p.name for p in find_audio(tmp_path)] == ["a.wav"]


def test_cli_usage_errors(tmp_path, capsys):
    assert main(["check", str(tmp_path / "missing")]) == 2
    assert main(["check", str(tmp_path)]) == 2
    assert "error" in capsys.readouterr().err


def test_cli_unreadable_file_listed_but_not_failing(tmp_path, capsys):
    (tmp_path / "bad.wav").write_bytes(b"not audio")
    assert main(["check", str(tmp_path)]) == 0
    assert "ERROR" in capsys.readouterr().out


def test_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert "bandcheck 0.1.0a1" in capsys.readouterr().out


# ---------------------------------------------------------------- tests added after the planted-bug check
def test_a_20_db_step_is_not_a_cutoff():
    """A shelf that drops 20 dB is below the 25 dB needed to call something a cut-off."""
    x = 0.1 * full(44100) + cut(44100, 16000)
    assert find_cliff(spec_of(x, 44100)) is None


def test_a_30_db_step_is_a_cutoff():
    x = 0.03 * full(44100) + cut(44100, 16000)
    c = find_cliff(spec_of(x, 44100))
    assert c is not None and abs(c.cutoff_hz - 16000) < 500


def test_quiet_full_band_passages_do_not_hide_a_cutoff():
    """Parts more than 30 dB under the loudest frame are ignored, so a quiet hiss does not fill in the empty band."""
    x = np.concatenate([cut(44100, 16000)[:44100 * 3], 0.03 * full(44100)[:44100 * 9]])     # 3 s loud, 9 s quiet
    c = find_cliff(mean_spectrum(synth.to_pcm16(x).astype(float) / 32767, 44100))
    assert c is not None and abs(c.cutoff_hz - 16000) < 500


def test_stereo_channels_are_averaged_so_a_full_band_channel_counts(tmp_path):
    p = tmp_path / "s.wav"
    sf.write(str(p), synth.to_pcm16(np.stack([cut(44100, 16000), full(44100)], axis=1)), 44100, subtype="PCM_16")
    assert check_file(p).status == OK


def test_a_long_file_is_judged_by_its_middle(tmp_path):
    x = np.concatenate([cut(44100, 16000)[:44100 * 4], full(44100)[:44100 * 4], cut(44100, 16000)[:44100 * 4]])
    p = write(tmp_path / "long.wav", x, 44100)
    xs, sr = load_mono(p, max_seconds=4)
    assert find_cliff(mean_spectrum(xs, sr)) is None            # the full-band middle, not the cut first 4 s


def test_spectrum_level_is_relative_to_its_loudest_bin():
    sp = spec_of(full(44100), 44100)
    assert sp.level_db.max() == pytest.approx(0.0, abs=1e-9) and sp.level_db.min() < -20
