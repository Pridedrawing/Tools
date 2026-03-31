#!/usr/bin/env python

import argparse
import sys

import config
import csv
import os
from elevenlabs import set_api_key, voices, Voice, VoiceSettings, generate, save, play


def _prompt_game(default_game_name: str) -> str:
    game_names = list(config.game_dict.keys())
    if default_game_name not in config.game_dict:
        default_game_name = game_names[0]

    print("Available games:")
    for idx, name in enumerate(game_names, start=1):
        marker = " (default)" if name == default_game_name else ""
        print(f"  {idx}) {name}{marker}")

    while True:
        raw = input(f"Select game [Enter={default_game_name}]: ").strip()
        if not raw:
            return default_game_name
        if raw.isdigit():
            selected_index = int(raw)
            if 1 <= selected_index <= len(game_names):
                return game_names[selected_index - 1]
            print("Invalid selection. Try again.")
            continue
        if raw in config.game_dict:
            return raw
        print("Unknown game name. Try again.")


parser = argparse.ArgumentParser(add_help=True)
parser.add_argument("--game", dest="game_name")
parser.add_argument("--lang", dest="lang")
parser.add_argument("--no-select", action="store_true")
parser.add_argument(
    "--dialogue",
    dest="dialogue_path",
    help="Path to dialogue file (defaults to Tools/Missing Files/dialogue_missing.tab if present)",
)
args = parser.parse_args()

selected_game_name = args.game_name or config.game_name
if (
    not args.no_select
    and not args.game_name
    and sys.stdin is not None
    and sys.stdin.isatty()
):
    selected_game_name = _prompt_game(selected_game_name)

if selected_game_name not in config.game_dict:
    print(f"Unknown game '{selected_game_name}'. Available: {', '.join(config.game_dict.keys())}")
    raise SystemExit(2)

selected_lang = args.lang or config.lang

script_dir = os.path.dirname(os.path.abspath(__file__))
default_dialogue_missing = os.path.normpath(
    os.path.join(script_dir, "..", "Missing Files", "dialogue_missing.tab")
)

dialogue_path = args.dialogue_path
if not dialogue_path:
    if os.path.exists(default_dialogue_missing):
        dialogue_path = default_dialogue_missing
    else:
        dialogue_path = config.filename

csv_path = dialogue_path if os.path.isabs(dialogue_path) else os.path.join(script_dir, dialogue_path)

delimiter = config.delimiter
if os.path.splitext(csv_path)[1].lower() in {".tab", ".tsv"}:
    delimiter = "\t"

game = config.game_dict[selected_game_name]
voice_dict = game["voices"]


savepath = game["savepath"] + "/"
if selected_lang != game["main_lang"]:
    savepath += (
        "tl/" + selected_lang + "/"
    )  # Descend into corresponding tl dir if voice not main lang
savepath += "audio/voice/"

model = "eleven_"
model += "multilingual"  # if lang == "English" else "multilingual"
model += "_v2"
set_api_key(config.api_key)

print("Game: " + selected_game_name)
print("Language: " + selected_lang)
print("Interpreted file: " + csv_path)
print("Example path: " + savepath + "[voice_id].mp3")
print('Example voice: "' + selected_game_name + ": " + '[character name]"')
print("================================")
print("Model: " + model)
print("API key: " + (config.api_key[:4] + "..." + config.api_key[-4:] if config.api_key else ""))
print("\n")
print("Make sure the dialogue file exists and has the expected columns!")
inchar = input("Are all the details correct? (y/n) ")
if inchar != "y":
    exit(1)

print("Caching voices...")
# voices()

file = open(csv_path, encoding="utf-8")
reader = csv.DictReader(
    file, delimiter=delimiter
)  # Interprets the CSV file as a dictionary
try:
    for row in reader:
        voice_dict[row["Character"]] == 0
        break
except KeyError as error:
    print(error)
    print("\n\n================================================================")
    print("Did you choose the right delimiter for the dialogue file?")
    printable_delimiter = delimiter.replace("\t", "\\t")
    print("The current one is: " + printable_delimiter)
    print("Hint: .tab/.tsv => tab delimiter, .csv => comma delimiter")
    print("================================================================\n\n")
for row in reader:
    if voice_dict[row["Character"]] in [0, 5]:
        continue
    voice = voice_dict[row["Character"]][1]  # Expects all voices to be their names
    print(voice_dict[row["Character"]][0], voice_dict[row["Character"]][1])
    audio = generate(
        text=row["Dialogue"],
        voice=Voice(
            voice_id=voice,
            settings=VoiceSettings(
                stability=0.5, similarity_boost=0.75, style=0.0, use_speaker_boost=True
            ),
            model=model,
        ),
    )
    play(audio)
    # path = savepath + row["Identifier"] + ".mp3"
    # # print(path + ", " + voice + ", " + row["Dialogue"])
    # save(audio, path);
