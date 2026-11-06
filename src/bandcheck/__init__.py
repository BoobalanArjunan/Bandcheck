"""bandcheck: does an audio file really hold the frequency range its sample rate promises?"""
from ._version import __version__
from .check import Verdict, check_file, judge

__all__ = ["__version__", "Verdict", "check_file", "judge"]
