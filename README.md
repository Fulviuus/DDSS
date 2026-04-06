# 🚨 DDSS - Dutch Detection & Suppression System

### *"Niente olandese in questa casa!"*

> A Raspberry Pi-powered linguistic enforcement device that listens to everything your kids say and punishes them with an ear-splitting siren when they dare to speak Dutch.

Because nothing says "healthy parenting" like a surveillance microphone wired to a smart speaker.

---

## The Problem

You're raising multilingual kids. That's great! Except they keep defaulting to Dutch at home, and your household rule is **Italian only**. You've tried reasoning. You've tried bribing. You've tried the disappointed Italian parent stare.

None of it worked.

So naturally, you built an AI-powered language detection system that blasts a siren through a Sonos speaker the moment it hears a single *"gezellig"*.

## How It Works

```
🎙️ Microphone ──► 🧠 Whisper AI ──► 🇳🇱 Dutch? ──► 🔊 WEEE-WOOO-WEEE-WOOO
     │                                    │
     │                                    ▼
     │                               🇮🇹 Italian?
     │                                    │
     └────────────────────────────────────┘
                                     (carry on)
```

1. **Listens** continuously via a USB microphone (Tonor TM20)
2. **Filters silence** using dual-layer VAD (webrtcvad + Whisper's built-in Silero VAD)
3. **Transcribes and detects language** using OpenAI's Whisper running locally — no cloud, no API fees, no evidence. You can even see what they said in the logs.
4. **Confirms with consensus** — requires 2 out of 3 consecutive chunks to detect Dutch before triggering, so a single mumble won't set it off
5. **Blasts a siren** on your Sonos speaker when Dutch is confirmed

The siren is a lovely two-tone 800Hz/1200Hz masterpiece, procedurally generated in memory. Think European ambulance, but for linguistic emergencies.

## Requirements

- **Raspberry Pi 5** (or any machine with a pulse and Python 3.10+)
- **USB Microphone** (tested with Tonor TM20, any USB mic works)
- **Sonos Speaker** on the same network
- A deep commitment to Italian language preservation

## Installation

```bash
git clone https://github.com/Fulviuus/DDSS.git
cd DDSS

python3 -m venv venv
source venv/bin/activate   # Linux/Mac
# venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

On Raspberry Pi, you'll also need:
```bash
sudo apt install libportaudio2 libsndfile1 python3-dev portaudio19-dev
```

## Configuration

Edit `config.yaml`:

```yaml
audio:
  device: null              # null = default, int = PortAudio index (Windows),
                            # string = ALSA device (Linux, e.g. "plughw:CARD=Device,DEV=0")
  chunk_seconds: 5          # audio chunk size for detection
  sample_rate: 16000

detection:
  model: "small"            # tiny | base | small (bigger = more accurate, slower)
  language_threshold: 0.5   # confidence threshold (0.0 - 1.0)
  target_language: "nl"     # the forbidden language
  cooldown_seconds: 10      # grace period between sirens (we're not monsters)

sonos:
  speaker_name: "Roam"      # your Sonos speaker name
  volume: 100               # siren volume (0-100, we recommend 100)
  siren_duration_seconds: 5 # how long the siren blasts
```

### Finding your audio device

**On Linux (Raspberry Pi):**
```bash
arecord -l
# Then use the ALSA device string, e.g. "plughw:CARD=Device,DEV=0"
```

**On Windows/Mac:**
```bash
python -c "import sounddevice; print(sounddevice.query_devices())"
# Then use the integer device index
```

## Usage

```bash
# Full mode: detect and blast
python -m ddss.main

# Dry run: detect only, no siren (for the faint of heart)
python -m ddss.main --dry-run --verbose

# With custom config
python -m ddss.main -c /path/to/config.yaml
```

### Sample Output

```
18:44:04 [INFO] ddss: DDSS - Dutch Detection & Suppression System
18:44:04 [INFO] ddss: Niente olandese in questa casa!
18:44:04 [INFO] ddss.detector: Loading Whisper model 'small'...
18:44:04 [INFO] ddss.actions: Found Sonos speaker: Roam (192.168.1.42)
18:44:04 [INFO] ddss: Listening... (cooldown=10s, threshold=50%)
18:44:25 [INFO] ddss.detector: Detected: it (95.7%) | "E' un quattro"
18:44:33 [INFO] ddss.detector: Detected: it (88.2%) | "Mamma, posso avere un gelato?"
18:44:41 [INFO] ddss.detector: Detected: nl (82.4%) | "Ik wil niet"
18:44:41 [INFO] ddss.detector: Target language match (1/1 in last 3 chunks, need 2)
18:44:49 [INFO] ddss.detector: Detected: nl (91.0%) | "Maar ik heb honger"
18:44:49 [WARNING] ddss: DUTCH DETECTED! (occurrence #1) — triggering action
18:44:49 [INFO] ddss.actions: Playing siren on 'Roam' at volume 100
18:44:55 [INFO] ddss.actions: Siren complete, volume restored to 30
```

## Auto-Start on Raspberry Pi

The service file uses `@` templating — pass your username after the `@`:

```bash
sudo cp systemd/ddss@.service /etc/systemd/system/
sudo systemctl enable ddss@$(whoami)
sudo systemctl start ddss@$(whoami)

# Check status
sudo systemctl status ddss@$(whoami)

# View logs
journalctl -u ddss@$(whoami) -f
```

## Targeting Other Languages

DDSS isn't just for Dutch suppression. Edit `target_language` in the config to persecute any language of your choice:

| Code | Language | Suggested Use Case |
|------|----------|--------------------|
| `nl` | Dutch | The original. The classic. |
| `de` | German | For when efficiency becomes too efficient |
| `fr` | French | Non |
| `en` | English | For the truly chaotic household |
| `it` | Italian | Wait, that defeats the purpose |

## FAQ

**Q: Is this ethical?**
A: We're not qualified to answer that. But the kids' Italian has improved dramatically.

**Q: What if it triggers on Afrikaans?**
A: Acceptable collateral damage. Whisper does sometimes confuse Dutch and Afrikaans. Consider it a feature.

**Q: Can I use this at the office?**
A: HR would like a word. But technically, yes.

**Q: The siren scared the cat.**
A: That's not a question. But yes, the cat now speaks Italian.

**Q: Does it work with dialects?**
A: Whisper handles standard Dutch well. If your kids start speaking Limburgish to bypass the system, congratulations — you've raised hackers.

**Q: It detected my kid saying "Ik wil niet" — what does that mean?**
A: "I don't want to." Ironic, because the siren doesn't care what they want.

## Tech Stack

- **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** — CTranslate2-optimized Whisper, 3-5x faster than vanilla, runs on Pi 5 with int8 quantization. Full transcription for accurate language detection.
- **[webrtcvad](https://github.com/wiseman/py-webrtcvad)** — Voice activity detection to skip silence
- **[pyalsaaudio](https://github.com/larsimmisch/pyalsaaudio)** — Direct ALSA audio capture on Linux (because PortAudio has opinions about Raspberry Pi)
- **[sounddevice](https://python-sounddevice.readthedocs.io/)** — Cross-platform audio capture fallback (Windows/Mac)
- **[SoCo](https://github.com/SoCo/SoCo)** — Sonos control library
- **numpy** — For generating the siren that haunts your children's dreams

## License

MIT — Do whatever you want with it. We take no responsibility for family therapy bills.

---

*Built with love, desperation, and a deep respect for the Italian language.* 🇮🇹
