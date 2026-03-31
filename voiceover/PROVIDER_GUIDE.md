# TTS Provider System - Usage Guide

## Overview
The voiceover system now supports multiple TTS providers through a flexible provider pattern. You can switch between ElevenLabs and Qwen TTS providers.

## Configuration

### In `config.py`:
```python
# TTS Provider Configuration
tts_provider = "elevenlabs"  # Options: "elevenlabs" or "qwen"
qwen_model_path = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
qwen_voices_dir = r"C:\Users\olli_\Documents\GitHub\Tools\Qwen\voices"
```

## Usage

### Using ElevenLabs (default):
```bash
python gen.py --game BEngel --lang English
```

Or explicitly:
```bash
python gen.py --game BEngel --lang English --provider elevenlabs
```

### Using Qwen:
```bash
python gen.py --game BEngel --lang English --provider qwen
```

### WSL2 (recommended for `flash-attn` on Windows)

On native Windows, `flash-attn` often requires a full CUDA Toolkit build setup (nvcc + build tools). If you want the speedup without fighting Windows builds, run Qwen under WSL2/Linux:

- Use the WSL config: `config_wsl.py`
- Run via the helper: `run_wsl.ps1`

In WSL, make sure you install Qwen deps (and `flash-attn`) into your WSL Python environment.

## Provider Comparison

| Feature | ElevenLabs | Qwen |
|---------|-----------|------|
| **Type** | Cloud API | Local Model |
| **API Key** | Required | Not needed |
| **Output** | MP3 | WAV |
| **Emotion Tags** | Supported (v3 model) | Not supported |
| **Voice Names** | "GameName: Character" | "GamePrefix_Character" |
| **Dependencies** | elevenlabs | torch, soundfile, qwen-tts |
| **Cost** | Per-character pricing | Free (after model download) |
| **Speed** | Fast (network dependent) | Slower (GPU dependent) |

## Requirements

### For ElevenLabs:
```bash
pip install elevenlabs
```
Set environment variable: `$Env:ELEVENLABS_API_KEY = "your_key"`

### For Qwen:
```bash
pip install torch soundfile qwen-tts
```
Ensure voice folders are set up in the configured `qwen_voices_dir` with:
- `GamePrefix_CharacterName/ref.wav`
- `GamePrefix_CharacterName/ref.txt`

## Voice Folder Structure (Qwen)

```
Qwen/voices/
├── BEngel_Ben/
│   ├── ref.wav
│   └── ref.txt
├── BEngel_Chris/
│   ├── ref.wav
│   └── ref.txt
├── BtC_Connor/
│   ├── ref.wav
│   └── ref.txt
...
```

## Architecture

The system uses a provider pattern with:
- **Base Interface**: `providers/base.py` - Abstract `TTSProvider` class
- **ElevenLabs**: `providers/elevenlabs_provider.py` - Cloud TTS implementation
- **Qwen**: `providers/qwen_provider.py` - Local voice cloning implementation
- **Factory**: `providers/__init__.py` - Provider selection logic

## Adding New Providers

To add a new TTS provider:

1. Create `providers/your_provider.py` extending `TTSProvider`
2. Implement required methods: `initialize()`, `get_supported_voices()`, `generate_audio()`, `get_file_extension()`
3. Add to factory in `providers/__init__.py`
4. Update config.py with any provider-specific settings
