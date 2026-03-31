# Pridedrawing Tools — Claude Code Context

Translation and voiceover pipeline for B_Engel, BoundToCollege, Gay-Office-Sim.

## Full Workflow (per language)

```
1. Ren'Py Launcher → Generate Translations
   → Creates .rpy files in game/tl/<language>/

2. Ren'Py Launcher → Extract Dialogue (select correct language!)
   → Exports dialogue.tab to repo root (e.g. B_Engel/dialogue.tab)

3. translate/translate.py
   → Reads dialogue.tab → DeepL → writes translated blocks into game/tl/<lang>/*.rpy
   → Requires: DEEPL_API_KEY in environment

4. Missing Files/missing_files.py
   → Compares dialogue.tab against game/audio/voice/
   → Output: dialogue_missing.tab + extra_files.csv

5. voiceover/gen.py
   → Reads dialogue_missing.tab → TTS provider → saves .mp3 files
   → Requires: ELEVENLABS_API_KEY (ElevenLabs) or local Qwen model

6. Repeat from step 2 for next language
```

## Key Rules

- Never commit `tl/` changes from game repos — managed by these scripts
- Never commit `set_env.ps1` — contains live API keys (gitignored)
- `dialogue.tab` must be extracted in the **correct target language** before use
- Scripts are Windows-native; Mac paths: `~/Projects/` instead of `C:\Users\olli_\Documents\GitHub\`

## Scripts

### translate/translate.py
- Translates dialogue via DeepL, writes `translate <lang> <id>:` blocks into .rpy files
- Config: `translate/config.py` — saves game/language selections between runs
- Supports glossaries (`glossaries.json`) for consistent character names
- Masks Ren'Py placeholders `[var]` and `{tag}` before translation

### Missing Files/missing_files.py
- Args: `[base_dir] [--dialogue path] [--lang English] [--ext .mp3]`
- `base_dir`: repo root (e.g. `~/Projects/B_Engel`) or `game/` subfolder
- Output: `dialogue_missing.tab` (feed into gen.py) + `extra_files.csv`
- Auto-detects language from dialogue.tab if `--lang` omitted

### voiceover/gen.py
- Interactive: select game, provider (elevenlabs/qwen), language, mode
- **Mode 1 (batch):** processes `dialogue_missing.tab`
- **Mode 2 (manual):** enter IDs one by one, plays back result, keep/regenerate/skip
- On skip: restores original file from `.bak` backup
- `dialogue.tab` is loaded from repo root (parent of `game/`)
- Duplicate IDs (multi-line translate blocks): uses first occurrence only
- Config: `voiceover/config.py` or `voiceover/config_11L.py`

### voiceover/providers/
- `elevenlabs_provider.py` — cloud TTS, MP3, voice name: `"GameName: Character"`
- `qwen_provider.py` — local voice cloning, WAV/MP3, voice name: `"GamePrefix_Character"`
  - Needs `ref.wav` + `ref.txt` per character in `qwen_voices_dir`
  - Does NOT support emotion tags — neutral output regardless of Ren'Py emotion

### Language Detection/language.py
- Detects language of each dialogue line via DeepL
- Requires: DEEPL_API_KEY

### Import_Transl/import_tansl.py
- Imports pre-translated CSV back into `tl/portuguese/*.rpy`
- Currently hardcoded to Portuguese — parameterize `tl_folder` for other languages

### VNavigator.py
- Parses .rpy for label/jump → generates .graphml story flowchart (yEd)

## API Keys

| Script | Key | File |
|--------|-----|------|
| translate.py | `DEEPL_API_KEY` | `Language Detection/set_env.ps1` |
| language.py | `DEEPL_API_KEY` | same |
| gen.py (ElevenLabs) | `ELEVENLABS_API_KEY` | `voiceover/set_env.ps1` |

Quick setup: `setup_keys.bat`

## Known Limitations

- Qwen TTS ignores Ren'Py emotion tags (surprised, lust, etc.) — always generates neutral tone
- Multi-line translate blocks share one ID — only the first line gets voiceover
- `dialogue.tab` must match the language being processed; wrong language = wrong audio
