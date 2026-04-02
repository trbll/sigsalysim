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
├── output/                     # Generated audio artifacts (CLI pipeline)
├── sigsaly/                    # Core DSP modules (documented, standalone-runnable)
│   ├── __init__.py
│   ├── telephone.py            # 1940s phone line simulation
│   ├── scrambler.py            # A-3 frequency inversion + cracker
│   ├── vocoder.py              # 10-band channel vocoder
│   ├── encryption.py           # One-time pad (mod-6 arithmetic)
│   └── key_generation.py       # Vinyl record key generator
├── web/                        # v2 Flask web dashboard
│   ├── app.py                  # Flask routes
│   ├── pipeline.py             # Structured pipeline orchestration
│   ├── spectrograms.py         # Matplotlib spectrogram generation
│   ├── templates/index.html    # Single-page UI
│   └── static/style.css        # Styling
├── scripts/
│   └── run_pipeline.py         # v1 CLI pipeline (all stages)
├── serve.sh                    # Multi-user server launcher (gunicorn)
├── venv/                       # Python virtual environment
└── README.md
```

## Roadmap

| Version | Status | Description |
|---------|--------|-------------|
| **v1 — CLI Pipeline** | ✅ Complete | Python modules + CLI script generating 18 audio files across 6 stages with quantitative diagnostics |
| **v2 — Web Dashboard** | ✅ Complete | Flask app wrapping v1: upload audio, tweak parameters (SNR, carrier freq, desync), view spectrograms and hear all outputs in the browser |
| **v3 — Interactive Visualization** | 🔜 Planned | Spinning vinyl record synchronization, real-time cracking workbench, FSK transmission simulation, dual turntable crossover, potentially networked two-party experience |

## Quick Start

### Setup

```bash
cd ~/Developer/sigsalysim
python3 -m venv venv
source venv/bin/activate
pip install numpy scipy soundfile matplotlib flask
```

### v2: Web Dashboard (recommended)

**Single user (local development / personal exploration):**

```bash
source venv/bin/activate
python web/app.py                     # starts on http://127.0.0.1:3001
python web/app.py --port 8080         # custom port
```

**Multi-user (classroom — students connect to your machine):**

```bash
pip install gunicorn                  # one-time setup
./serve.sh                            # 8 workers on port 3001
./serve.sh --workers 12 --port 8080   # custom
```

Students connect to `http://your-hostname.local:3001` (or your IP address). Each worker handles one pipeline run at a time — with 8 workers, 8 students can process simultaneously; additional requests queue automatically. See `serve.sh` for recommended worker counts by class size.

Open the URL in your browser. Upload a WAV file (or use the built-in sample), adjust parameters with sliders, and click **Run Pipeline**. All 17 audio outputs appear with spectrograms, audio players, and diagnostic text. Uploaded audio is limited to 120 seconds.

**Features:**
- Source audio preview player (always visible for A/B comparison)
- Spectrogram visualizations for every output (visual comparison is very compelling)
- Parameter sliders: telephone SNR (10-50 dB), A-3 carrier frequency (500-5000 Hz), desync offset (1-100 frames)
- Grouped by stage with educational descriptions and quantitative diagnostics
- Security comparison summary at the bottom

### v1: CLI Pipeline

```bash
source venv/bin/activate
python scripts/run_pipeline.py
```

This generates **18 audio files** in `output/` and prints detailed diagnostics explaining the quantitative "why" behind each stage.

### Use Your Own Audio

```bash
python scripts/run_pipeline.py path/to/your_voice.wav output_custom/
```

Any mono or stereo WAV file will work. The pipeline normalizes and processes it automatically.

### Run Individual Modules

Each module works standalone for focused exploration. Run any module with no arguments to see its full help text.

#### Telephone Line Simulation

```bash
python -m sigsaly.telephone <input.wav> <output.wav> [snr_db]
```

| Parameter | Description | Default |
|-----------|-------------|---------|
| `input.wav` | Source audio file | *(required)* |
| `output.wav` | Output audio file | *(required)* |
| `snr_db` | Signal-to-noise ratio in decibels. Lower = noisier. **40** = clean modern line, **30** = typical 1940s domestic, **25** = 1940s transatlantic, **20** = poor connection, **10** = barely usable | `30` |

```bash
python -m sigsaly.telephone input/sample_speech.wav output/phone.wav         # standard line
python -m sigsaly.telephone input/sample_speech.wav output/noisy.wav 20      # poor connection
python -m sigsaly.telephone input/sample_speech.wav output/terrible.wav 10   # barely usable
```

#### A-3 Frequency Inversion Scrambler

```bash
python -m sigsaly.scrambler <mode> <input.wav> <output.wav> [carrier_freq]
```

| Parameter | Description | Default |
|-----------|-------------|---------|
| `mode` | One of: **scramble** (apply A-3), **unscramble** (reverse with known carrier), **crack** (automated spectral analysis attack) | *(required)* |
| `input.wav` | Source audio file | *(required)* |
| `output.wav` | Output audio file | *(required)* |
| `carrier_freq` | Carrier frequency in Hz (the "secret key"). Only used in scramble/unscramble modes. The A-3 used values around 2000-3000 Hz. | `2000` |

```bash
# Scramble with a specific carrier frequency
python -m sigsaly.scrambler scramble input/sample_speech.wav output/scrambled.wav 2000

# Unscramble (you must know the carrier frequency)
python -m sigsaly.scrambler unscramble output/scrambled.wav output/recovered.wav 2000

# Automated cracking — finds the carrier frequency and recovers speech
python -m sigsaly.scrambler crack output/scrambled.wav output/cracked.wav
```

#### Channel Vocoder

```bash
python -m sigsaly.vocoder <input.wav> <output.wav>
```

| Parameter | Description |
|-----------|-------------|
| `input.wav` | Source speech audio |
| `output.wav` | Vocoder-resynthesized output |

```bash
python -m sigsaly.vocoder input/sample_speech.wav output/vocoded.wav
```

The output sounds robotic but intelligible — 10 frequency bands, 6 amplitude levels, 50 frames/sec.

#### Key Record Generation

```bash
python -m sigsaly.key_generation <duration_seconds> [seed] [output_dir]
```

| Parameter | Description | Default |
|-----------|-------------|---------|
| `duration_seconds` | Length of key material in seconds. Real SIGSALY records held 12 minutes (720s). | *(required)* |
| `seed` | Random seed for reproducibility. Use `None` for true randomness. **Warning**: seeds make keys predictable — real SIGSALY used hardware noise. | `None` |
| `output_dir` | Directory for output files | `output/` |

Generates two files:
- **`key_record.npz`** — the key data (for encryption/decryption)
- **`key_record.wav`** — the key as **audible audio**: what the vinyl record sounded like if you played it on a phonograph. It's noise — because that's literally what was recorded on the real SIGSALY key records (mercury-vapor tube thermal noise). Listening to it helps you understand why subtracting random noise from speech destroys all structure.

```bash
python -m sigsaly.key_generation 30              # 30s of key material
python -m sigsaly.key_generation 10 42           # reproducible with seed
python -m sigsaly.key_generation 720             # full 12-minute record (like real SIGSALY)
```

#### Encryption Demo

```bash
python -m sigsaly.encryption
```

No parameters — prints the complete mod-6 arithmetic table showing every possible encryption/decryption combination. Useful for understanding the one-time pad math.

## Output Files — Listening Guide

| Stage | Files | What You'll Hear |
|-------|-------|-----------------|
| **0 — Original** | `0a_original.wav`, `0b_..._telephone.wav` | Clean speech, then the same voice through a 1940s phone line (bandlimited, noisy) |
| **1 — A-3 Scrambler** | `1a_a3_scrambled.wav`, `1b_..._telephone.wav` | Garbled alien-sounding audio. Sounds secure... |
| **1 — A-3 Cracked** | `1c_a3_cracked.wav`, `1d_..._telephone.wav` | ...but spectral analysis recovers the speech! The "secret" was just one number. |
| **2 — Vocoder** | `2a_vocoder.wav`, `2b_..._telephone.wav` | Robotic but intelligible — the characteristic "SIGSALY sound" |
| **3 — SIGSALY Encrypted** | `3a_sigsaly_encrypted.wav`, `3b_..._telephone.wav` | Pure noise. No speech structure whatsoever. |
| **3 — SIGSALY Decrypted** | `3c_sigsaly_decrypted.wav`, `3d_..._telephone.wav` | Vocoded speech restored — decryption works! |
| **3 — Key Record** | `3e_key_record_audio.wav` | What the vinyl key record sounded like — pure random noise from mercury-vapor tubes. This is the physical one-time pad. |
| **4 — Crack Attempt** | `4a_sigsaly_a3crack_attempt.wav` | A-3 cracking method applied to SIGSALY — still noise. Spectral analysis fails. |
| **5 — Clock Desync** | `5a_desync_1frame.wav` ... `5c_desync_25frames.wav` | Even 20ms of turntable misalignment = complete garbage |

## Key Diagnostic Outputs

The pipeline and individual modules print quantitative insights. Run any module with the `verbose=True` flag (enabled by default in CLI mode) to see these:

- **Compression ratio**: The vocoder achieves 37:1 compression (22,050 values/sec → 600 values/sec)
- **Quantization distribution**: How the 6 levels (0–5) are distributed across band amplitudes, showing companding's effect
- **Encryption uniformity**: Encrypted values should be uniformly distributed (chi-squared test). Correlation between original and encrypted should be ~0.0.
- **Desync accuracy**: With perfect sync, 100% of values match. With ANY offset, accuracy drops to ~16.7% (= 1/6, random chance). This is the one-time pad's all-or-nothing property.
- **A-3 cracking confidence**: The spectral analysis cracker reports its top candidates and a confidence ratio. High confidence on A-3 audio, low confidence (failure) on SIGSALY audio.
- **Key randomness verification**: Distribution uniformity and sequential correlation checks confirm the key has no detectable patterns.

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
