# Pridedrawing Tools

Translation and voiceover pipeline for B_Engel, BoundToCollege, Gay-Office-Sim and Heritage.

---

## Overview

```
Ren'Py Launcher
    │
    ▼
Extract Dialogue ──► dialogue.tab
    │
    ▼
translate.py ──────► game/tl/<lang>/*.rpy  (translated dialogue)
    │
    ▼
missing_files.py ──► dialogue_missing.tab  (lines without audio)
    │
    ▼
gen.py ─────────────► game/audio/voice/*.mp3  (generated voiceover)
    │
    ▼
Repeat for next language
```

---

## Step-by-Step Workflow

### 1. Generate translation files (Ren'Py Launcher)

In the Ren'Py Launcher, go to **Generate Translations** and generate the target language. This creates the empty `.rpy` translation files under `game/tl/<language>/`.

> Do this once per language before running the translation script.

---

### 2. Extract dialogue (Ren'Py Launcher)

In the Ren'Py Launcher, use **Extract Dialogue** to export a `dialogue.tab` file for the target language. Place it in the game root or point to it via config.

---

### 3. Translate dialogue (`translate/translate.py`)

Translates dialogue lines via **DeepL** and writes them into the `.rpy` translation files.

**Setup (first time):**
```bat
cd translate
setup.bat          # installs dependencies (deepl)
```

Set your DeepL API key:
```powershell
cd "Language Detection"
copy set_env.ps1.example set_env.ps1
# Edit set_env.ps1 and insert your DEEPL_API_KEY
. .\set_env.ps1
```

**Run:**
```bat
cd translate
run.bat
```

The script will prompt you to confirm or change:
- Game
- Language folder (e.g. `English`, `portuguese`)
- DeepL target language (auto-suggested from folder name)
- Dialogue file path

Selections are saved to `config.py` for next run.

> **Tip:** Use *strings-only mode* to only translate UI strings without re-running all dialogue.

---

### 4. Find missing audio files (`Missing Files/missing_files.py`)

Compares the dialogue export against existing audio files to find lines without voiceover.

**Run:**
```bat
cd "Missing Files"
run_missing_files.bat
```

**Outputs:**
- `dialogue_missing.tab` — lines that need voiceover → used by `gen.py`
- `extra_files.csv` — audio files that exist but are no longer in the dialogue

---

### 5. Generate voiceover (`voiceover/gen.py`)

Generates audio files from `dialogue_missing.tab` using **ElevenLabs** (cloud) or **Qwen TTS** (local).

**Setup (first time):**
```bat
cd voiceover
setup.bat
copy set_env.ps1.example set_env.ps1
# Edit set_env.ps1 and insert your ELEVENLABS_API_KEY
```

**Run (ElevenLabs):**
```powershell
. .\set_env.ps1
python gen.py --game BEngel --lang English
```

**Run (batch, no prompts):**
```powershell
python gen.py --no-select --dialogue "..\Missing Files\dialogue_missing.tab" --log log.txt
```

**Providers:**

| Provider | Key needed | Output | Notes |
|----------|-----------|--------|-------|
| ElevenLabs | `ELEVENLABS_API_KEY` | .mp3 | Cloud, fast |
| Qwen TTS | None | .wav | Local model, free, needs GPU |

Switch provider in `voiceover/config.py`:
```python
tts_provider = "elevenlabs"  # or "qwen"
```

**Voice assignment** is defined in `voices.txt` — maps character shortcodes (e.g. `t`, `j`, `s`) to ElevenLabs voice IDs.

---

### 6. Repeat for the next language

Go back to step 2, extract dialogue for the next language, and run through steps 3–5 again.

---

## Tools Overview

| Folder | Script | Purpose |
|--------|--------|---------|
| `translate/` | `translate.py` | DeepL translation → .rpy files |
| `Missing Files/` | `missing_files.py` | Find dialogue lines without audio |
| `voiceover/` | `gen.py` | Generate .mp3/.wav voiceover |
| `Language Detection/` | `language.py` | Detect language of dialogue lines (DeepL) |
| `Import_Transl/` | `import_tansl.py` | Import CSV translations → .rpy (Portuguese) |
| `VNavigator.py` | — | Generate story flow chart (yEd .graphml) |

---

## API Keys

Keys are stored locally in `set_env.ps1` files — **never commit them to GitHub.**

```
Tools/
├── voiceover/set_env.ps1          ← ELEVENLABS_API_KEY
└── Language Detection/set_env.ps1 ← DEEPL_API_KEY
```

Quick setup:
```bat
setup_keys.bat   ← guided setup for all keys at once
```

---

## Important Rules

- **Never commit `tl/` folder changes** from game repos — translations are managed by these scripts
- **Never commit `set_env.ps1`** — it contains live API keys and is gitignored
- Scripts are Windows-native (`C:\Users\olli_\Documents\GitHub\...`) — adjust paths for other systems
