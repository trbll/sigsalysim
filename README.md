# SIGSALY Simulator

An educational simulation of the **SIGSALY** secure voice communication system used during World War II (1943–1946) for encrypted conversations between Allied leaders, including Roosevelt and Churchill.

Built for students studying **IoT Security and Cybersecurity** — SIGSALY is a compelling case study because it combines intuitive building blocks (filters, quantization, modular arithmetic) into a system with provably perfect security.

## What is SIGSALY?

SIGSALY was the first digital, encrypted voice communication system. Before SIGSALY, the Allies used the **A-3 scrambler**, which simply flipped the audio frequency spectrum. The Germans cracked it routinely using spectral analysis by 1941.

SIGSALY's breakthrough was a fundamentally different approach:

1. **Vocoder** — Decompose speech into 10 frequency band amplitudes + pitch (50 times/sec)
2. **Quantize** — Map each parameter to 6 discrete levels (0–5) using companding
3. **Encrypt** — Subtract a random key value (mod 6) from each parameter
4. **Transmit** — Send encrypted values over the phone line
5. **Decrypt** — Add the same key value (mod 6) at the receiver
6. **Resynthesize** — Feed decrypted parameters into the vocoder to produce audible speech

The encryption key was stored on **vinyl phonograph records** filled with random noise from mercury-vapor vacuum tubes. Identical copies were shipped by armed courier to each terminal. Each record was used exactly once and then destroyed — a physical **one-time pad**.

### Why is it unbreakable?

Claude Shannon proved in 1949 that a one-time pad achieves *perfect secrecy*: the encrypted output is statistically independent of the input. No amount of computation or analysis can recover the original message without the key. This requires three conditions:

1. The key must be **truly random** (SIGSALY: vacuum tube thermal noise)
2. The key must be **at least as long** as the message (12-minute vinyl records)
3. The key must **never be reused** (records destroyed after use)

### Why did it need precise clocks?

Both terminals played their vinyl key records simultaneously. If the turntables were even slightly out of sync (20ms = one frame), the receiver would use the wrong key values for every frame — producing complete garbage. The simulator demonstrates this dramatically.

## Repository Structure

```
sigsalysim/
├── input/                      # Source audio files
│   └── sample_speech.wav       # Default sample (generated via macOS TTS)
├── output/                     # Generated audio artifacts (17 WAV files)
├── sigsaly/                    # Core modules (documented, standalone-runnable)
│   ├── __init__.py
│   ├── telephone.py            # 1940s phone line simulation
│   ├── scrambler.py            # A-3 frequency inversion + cracker
│   ├── vocoder.py              # 10-band channel vocoder
│   ├── encryption.py           # One-time pad (mod-6 arithmetic)
│   └── key_generation.py       # Vinyl record key generator
├── scripts/
│   └── run_pipeline.py         # Full demo pipeline (all stages)
├── venv/                       # Python virtual environment
└── README.md
```

## Quick Start

### Setup

```bash
cd ~/Developer/sigsalysim
python3 -m venv venv
source venv/bin/activate
pip install numpy scipy soundfile matplotlib
```

### Run the Full Pipeline

```bash
source venv/bin/activate
python scripts/run_pipeline.py
```

This generates **17 audio files** in `output/` and prints detailed diagnostics explaining the quantitative "why" behind each stage.

### Use Your Own Audio

```bash
python scripts/run_pipeline.py path/to/your_voice.wav output_custom/
```

Any mono or stereo WAV file will work. The pipeline normalizes and processes it automatically.

### Run Individual Modules

Each module works standalone for focused exploration:

```bash
# Telephone line simulation
python -m sigsaly.telephone input/sample_speech.wav output/phone.wav
python -m sigsaly.telephone input/sample_speech.wav output/noisy.wav 20  # noisier line

# A-3 scrambler
python -m sigsaly.scrambler scramble input/sample_speech.wav output/scrambled.wav 2000
python -m sigsaly.scrambler crack output/scrambled.wav output/cracked.wav

# Vocoder (analysis + resynthesis)
python -m sigsaly.vocoder input/sample_speech.wav output/vocoded.wav

# Key generation
python -m sigsaly.key_generation 30  # 30 seconds of key material

# Encryption demo (mod-6 arithmetic table)
python -m sigsaly.encryption
```

## Output Files — Listening Guide

| Stage | Files | What You'll Hear |
|-------|-------|-----------------|
| **0 — Original** | `0a_original.wav`, `0b_original_telephone.wav` | Clean speech, then the same voice through a 1940s phone line (bandlimited, noisy) |
| **1 — A-3 Scrambler** | `1a_a3_scrambled.wav`, `1b_..._telephone.wav` | Garbled alien-sounding audio. Sounds secure... |
| **1 — A-3 Cracked** | `1c_a3_cracked.wav`, `1d_..._telephone.wav` | ...but spectral analysis recovers the speech! The "secret" was just one number. |
| **2 — Vocoder** | `2a_vocoder.wav`, `2b_..._telephone.wav` | Robotic but intelligible — the characteristic "SIGSALY sound" |
| **3 — SIGSALY Encrypted** | `3a_sigsaly_encrypted.wav`, `3b_..._telephone.wav` | Pure noise. No speech structure whatsoever. |
| **3 — SIGSALY Decrypted** | `3c_sigsaly_decrypted.wav`, `3d_..._telephone.wav` | Vocoded speech restored — decryption works! |
| **4 — Crack Attempt** | `4a_sigsaly_a3crack_attempt.wav` | A-3 cracking method applied to SIGSALY — still noise. Spectral analysis fails. |
| **5 — Clock Desync** | `5a_desync_1frame.wav` ... `5c_desync_25frames.wav` | Even 20ms of turntable misalignment = complete garbage |

## Key Diagnostic Outputs

The pipeline and individual modules print quantitative insights:

- **Compression ratio**: The vocoder achieves 37:1 compression (22,050 values/sec → 600 values/sec)
- **Quantization distribution**: How the 6 levels (0–5) are distributed across band amplitudes, showing companding's effect
- **Encryption uniformity**: Encrypted values should be uniformly distributed (chi-squared test). Correlation between original and encrypted should be ~0.0.
- **Desync accuracy**: With perfect sync, 100% of values match. With ANY offset, accuracy drops to ~16.7% (= 1/6, random chance). This is the one-time pad's all-or-nothing property.
- **A-3 cracking confidence**: The spectral analysis cracker reports its top candidates and a confidence ratio. High confidence on A-3 audio, low confidence (failure) on SIGSALY audio.

## Security Concepts Demonstrated

| Concept | Where You See It |
|---------|-----------------|
| **Security through obscurity fails** | A-3 scrambler cracked in Stage 1 |
| **One-time pad / perfect secrecy** | SIGSALY encryption in Stage 3 |
| **Key distribution problem** | Physical vinyl records, armed couriers |
| **Clock synchronization** | Desync demo in Stage 5 |
| **Quantization / digitization** | Vocoder's 6-level companding in Stage 2 |
| **Modular arithmetic** | Mod-6 encrypt/decrypt throughout |
| **Spectral analysis attacks** | Automated cracker in Stage 1 / failed crack in Stage 4 |
| **Compression as enabling technology** | Vocoder's 37:1 ratio makes encryption feasible |

## How the Modules Work

### `telephone.py` — Phone Line Simulation
Applies bandpass filtering (300–3400 Hz), tube amplifier distortion (tanh soft-clipping), and additive white Gaussian noise to simulate a 1940s long-distance connection.

### `scrambler.py` — A-3 Frequency Inversion
Multiplies the signal by a cosine carrier wave, then lowpass filters to keep only the frequency-inverted baseband. The cracker tries different carrier frequencies and scores how "speech-like" each result is (low spectral centroid + high spectral variance = speech).

### `vocoder.py` — Channel Vocoder
Splits speech into 10 frequency bands, extracts the amplitude envelope of each using the Hilbert transform, detects pitch via autocorrelation, and quantizes everything to 6 levels with mu-law companding. Resynthesis uses pulse trains (voiced) or white noise (unvoiced) filtered through the same band structure.

### `encryption.py` — One-Time Pad
Subtracts random key values from vocoder parameters using modular arithmetic: `encrypted = (value - key) mod 6`. Decryption adds: `decrypted = (encrypted + key) mod 6`. Also implements timing offset simulation for the desync demo.

### `key_generation.py` — Vinyl Record Simulator
Generates arrays of random integers matching the vocoder parameter structure. Supports save/load (simulating record pressing and turntable playback) and duplication (simulating the manufacturing of matched record pairs).

## References

- [SIGSALY — Wikipedia](https://en.wikipedia.org/wiki/SIGSALY)
- [99% Invisible: Vox Ex Machina](https://99percentinvisible.org/episode/vox-ex-machina/) — podcast episode on SIGSALY
- [99% Invisible: Numbers Stations](https://99percentinvisible.org/episode/numbers-stations/) — related episode on encrypted communications
- Shannon, C.E. (1949). "Communication Theory of Secrecy Systems." *Bell System Technical Journal*, 28(4), 656–715.
