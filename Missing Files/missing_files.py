import argparse
import csv
import os
import re
import subprocess
import sys

# Function to check if a package is installed
def check_and_install(package):
    try:
        __import__(package)
    except ImportError:
        user_input = input(f"The package '{package}' is not installed. Do you want to install it? (yes/no): ").strip().lower()
        if user_input == 'yes':
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
        else:
            print(f"The package '{package}' is required. Exiting.")
            exit()

# Check and install necessary packages
check_and_install('pandas')

import pandas as pd

parser = argparse.ArgumentParser(description="Detect missing audio files based on a dialogue.tab export")
parser.add_argument(
    "base_dir",
    nargs="?",
    help=(
        "Base directory (repo root containing 'game/', or the 'game/' directory itself). "
        "If omitted, you will be prompted."
    ),
)
parser.add_argument(
    "--dialogue",
    dest="dialogue_path",
    help="Path to dialogue.tab (default: <base_dir>/dialogue.tab)",
)
parser.add_argument(
    "--lang",
    dest="lang",
    help="Ren'Py tl language folder (e.g., English, German). If set, checks game/tl/<lang>/audio/voice",
)
parser.add_argument(
    "--ext",
    dest="ext",
    default=".mp3",
    help="Audio file extension to check (default: .mp3)",
)
args = parser.parse_args()


def _prompt_if_missing(value: str | None, prompt: str) -> str:
    if value:
        return value
    return input(prompt).strip()


def _pick_base_dir_from_defaults() -> str:
    github_root = r"C:\Users\olli_\Documents\GitHub"
    candidates = [
        ("B_Engel", os.path.join(github_root, "B_Engel")),
        ("BoundToCollege", os.path.join(github_root, "BoundToCollege")),
        ("Gay-Office-Simulator", os.path.join(github_root, "Gay-Office-Simulator")),
        # Common alternate folder name
        ("Gay-Office-Sim", os.path.join(github_root, "Gay-Office-Sim")),
    ]

    existing = [(name, path) for name, path in candidates if os.path.isdir(path)]
    if not existing:
        return _prompt_if_missing(
            None,
            "Enter the base directory (repo root containing 'game/', or the 'game/' directory itself): ",
        )

    print("Select game base directory:")
    for idx, (name, path) in enumerate(existing, start=1):
        print(f"  {idx}) {name} -> {path}")
    print("  0) Enter a custom path")

    while True:
        raw = input("Your choice: ").strip()
        if raw == "0":
            return _prompt_if_missing(
                None,
                "Enter the base directory (repo root containing 'game/', or the 'game/' directory itself): ",
            )
        if raw.isdigit():
            selected = int(raw)
            if 1 <= selected <= len(existing):
                return existing[selected - 1][1]
        print("Invalid selection. Enter a number from the list.")


def _resolve_game_dir(base_dir: str) -> str:
    base_dir = os.path.abspath(base_dir)
    # If user points directly at the game directory
    if os.path.isdir(os.path.join(base_dir, "audio")):
        return base_dir
    candidate = os.path.join(base_dir, "game")
    if os.path.isdir(candidate):
        return candidate
    raise FileNotFoundError(
        "Could not find 'game' directory. Provide either the repo root containing 'game/', or the 'game/' folder itself."
    )


_TL_LANG_RE = re.compile(r"(?:^|/)game/tl/([^/]+)/", flags=re.IGNORECASE)


def _infer_lang_from_dialogue(df: pd.DataFrame) -> str | None:
    if "Filename" not in df.columns:
        return None
    values = df["Filename"].dropna().astype(str).tolist()
    langs: list[str] = []
    for value in values[:5000]:
        match = _TL_LANG_RE.search(value.replace("\\", "/"))
        if match:
            langs.append(match.group(1))
    if not langs:
        return None
    # Most common
    return max(set(langs), key=langs.count)


def _audio_dir(game_dir: str, lang: str | None) -> str:
    if lang:
        return os.path.join(game_dir, "tl", lang, "audio", "voice")
    return os.path.join(game_dir, "audio", "voice")


base_dir = args.base_dir or _pick_base_dir_from_defaults()
game_dir = _resolve_game_dir(base_dir)

# Set the path to the dialogue.tab file
dialogue_path = args.dialogue_path or os.path.join(os.path.abspath(base_dir), "dialogue.tab")

if not os.path.exists(dialogue_path):
    print(f"The file '{dialogue_path}' does not exist. Please check the path and try again.")
    exit()

# Read the text file with tab separator
spreadsheet = pd.read_csv(dialogue_path, sep="\t")

# Column name in the spreadsheet that contains the audio file names
file_name_column = "Identifier"

if file_name_column not in spreadsheet.columns:
    print(
        f"Expected column '{file_name_column}' not found in '{dialogue_path}'. "
        f"Columns found: {', '.join(spreadsheet.columns.astype(str))}"
    )
    exit()

spreadsheet[file_name_column] = spreadsheet[file_name_column].astype(str).str.strip()
spreadsheet = spreadsheet[spreadsheet[file_name_column].notna() & (spreadsheet[file_name_column] != "")]

selected_lang = args.lang
if selected_lang is None:
    inferred = _infer_lang_from_dialogue(spreadsheet)
    if inferred:
        raw = input(
            f"Detected language folder from dialogue: '{inferred}'. Press Enter to use it, or type a different one, or leave blank for main language audio: "
        ).strip()
        selected_lang = raw or inferred
    else:
        raw = input(
            "Optional: enter tl language folder to check (e.g., English). Leave blank to check main audio folder: "
        ).strip()
        selected_lang = raw or None

audio_folder_path = _audio_dir(game_dir, selected_lang)

if not os.path.exists(audio_folder_path):
    print(f"The audio folder '{audio_folder_path}' does not exist. Please check the path and try again.")
    exit()

ext = args.ext
if not ext.startswith("."):
    ext = "." + ext
ext = ext.lower()


def _normalize_identifier(name: str) -> str:
    return name.strip().lower()


# Recursively gather audio files and normalize case (Windows is case-insensitive, but Python sets are not)
audio_files_map: dict[str, list[str]] = {}
for root, _dirs, files in os.walk(audio_folder_path):
    for file in files:
        if os.path.splitext(file)[1].lower() != ext:
            continue
        stem = os.path.splitext(file)[0]
        key = _normalize_identifier(stem)
        audio_files_map.setdefault(key, []).append(os.path.join(root, file))

audio_files = set(audio_files_map.keys())
spreadsheet_files = set(_normalize_identifier(v) for v in spreadsheet[file_name_column].astype(str).tolist())

missing_files = spreadsheet_files - audio_files
extra_files = audio_files - spreadsheet_files

# Output the missing files
if missing_files:
    print("The following files are missing from the folder:")
    for file in sorted(missing_files):
        print(file)
else:
    print("No files are missing.")

# Output the extra files
if extra_files:
    print("\nThe following files are in the folder but not listed in the spreadsheet:")
    for file in sorted(extra_files):
        print(file)
else:
    print("All files in the folder are listed in the spreadsheet.")

script_dir = os.path.dirname(os.path.abspath(__file__))
extra_files_csv_path = os.path.join(script_dir, "extra_files.csv")

# Always write extra files report (even if empty)
with open(extra_files_csv_path, "w", newline="", encoding="utf-8") as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["identifier_normalized", "path"])
    for file_key in sorted(extra_files):
        paths = audio_files_map.get(file_key, [])
        if not paths:
            writer.writerow([file_key, ""])
            continue
        for path in sorted(paths):
            writer.writerow([file_key, path])

# Filter the spreadsheet to keep only rows with missing files (case-insensitive)
missing_keys = set(missing_files)
missing_files_df = spreadsheet[
    spreadsheet[file_name_column].astype(str).map(_normalize_identifier).isin(missing_keys)
]

# Save the filtered dataframe to a new tab-separated file
missing_files_df.to_csv("dialogue_missing.tab", sep="\t", index=False)

# Display summary
print("\nSummary:")
print(f"Dialogue: {dialogue_path}")
print(f"Game dir: {game_dir}")
print(f"Audio dir: {audio_folder_path}")
print(f"Extension: {ext}")
print(f"Number of missing files: {len(missing_files)}")
print(f"Number of files not listed in the spreadsheet: {len(extra_files)}")
print(f"Extra files CSV: {extra_files_csv_path}")
