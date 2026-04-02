"""
SIGSALY Simulator
=================
An educational simulation of the SIGSALY secure voice communication system
used during World War II (1943-1946) for encrypted conversations between
Allied leaders including Roosevelt and Churchill.

This package implements the full SIGSALY signal processing pipeline:

  telephone.py      — 1940s long-distance phone line simulation
  scrambler.py      — A-3 frequency inversion (pre-SIGSALY, crackable)
  vocoder.py        — 10-band channel vocoder (analysis + resynthesis)
  encryption.py     — One-time pad encryption (mod-6 arithmetic)
  key_generation.py — Random key record generation ("vinyl records")

Each module can be run standalone or composed via the pipeline script.
All modules print diagnostic/quantitative output to help students
understand the "why" behind how each stage sounds.

Historical context:
  Before SIGSALY, the Allies used the A-3 scrambler, which the Germans
  were routinely cracking via spectral analysis by 1941. SIGSALY replaced
  this with a fundamentally different approach: digitize speech with a
  vocoder, encrypt the digital parameters with a one-time pad, and
  transmit the result. The one-time pad is provably unbreakable
  (Shannon, 1949) — a property no amount of spectral analysis can defeat.
"""
