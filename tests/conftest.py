import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent))
import synth  # noqa: E402


@lru_cache(maxsize=None)
def full(sr, seed=0, seconds=12.0):
    return synth.make_full(sr, seconds, seed)


@lru_cache(maxsize=None)
def cut(sr, cutoff_hz, seed=0, seconds=12.0, transition_hz=400.0):
    return synth.lowpass(full(sr, seed, seconds), sr, cutoff_hz, transition_hz)


@lru_cache(maxsize=None)
def up(sr, from_sr, seed=0, seconds=12.0):
    return synth.upsampled(sr, from_sr, seconds, seed)


def write(path, x, sr):
    """16-bit PCM, like most real files."""
    sf.write(str(path), synth.to_pcm16(x), sr, subtype="PCM_16")
    return path
