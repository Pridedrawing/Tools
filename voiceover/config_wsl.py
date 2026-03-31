"""WSL-specific config for Tools/voiceover.

This lets you run gen.py under WSL2/Linux while keeping the normal Windows
config.py unchanged.

Usage (PowerShell):
  $Env:VOICEOVER_CONFIG = 'config_wsl'
  python gen.py --provider qwen
"""

import os

game_name = "BEngel"  # Corresponds to game name in 'game_dict' and ElevenLabs: "Bound To College", "BEngel", or "GOS"
lang = "English"  # Corresponds to 'game/tl/[lang]/'

# TTS Provider Configuration
tts_provider = "elevenlabs"  # Options: "elevenlabs" or "qwen"
qwen_model_path = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"

# WSL2 path (Windows: C:\Users\olli_\Documents\GitHub\Tools\Qwen\voices)
qwen_voices_dir = "/mnt/c/Users/olli_/Documents/GitHub/Tools/Qwen/voices"

################################################################################

# Defines the voices' dictionary
# Mind the trailing commas!
bengel_voices = {
    "a": "Alien",
    "b": "Ben",
    "c": "Chris",
    "d": "Ben", 	# As the demonised version of himself
    "e": "Elijah",
    "dog": "Demon",
    "h": "Hartmann",
    "horse": "Marvin",
    "j": "Jeff",
    "k": "Kyle",
    "l": "Lucifer",
    "m": "Marvin",
    "n": "Noah",
    "md": "Marvin",
    "s": "Sabrina",
    "t": "Tim",
    "z": 0, 		# Ignored
    "": "Narrator",
    "centered": "Narrator",

    "e_nvl": "Sabrina",  # Sabrina on the phone
    "n_nvl": "Jeff" 	# Jeff on the phone
}

btc_voices = {
    "": "Narrator",
    "a": "Administrator",
    "A": "Administrator",
    "c": "Connor",
    "C": "Connor",
    "h": "Headmaster",
    "H": "Headmaster",
    "j": "Julian",
    "J": "Julian",
    "dog": "Julian",
    "jc": "Julio",
    "JC": "Julio",
    "jk": "Jupiter",
    "JK": "Jupiter",
    "ma": "Max",
    "MA": "Max",
    "m": "Mistress",
    "M": "Mistress",
    "n": "Ned",
    "N": "Ned",
    "na": "Nathan",
    "NA": "Nathan",
    "r": "Ron",
    "R": "Ron",
    "t": "Tom",
    "T": "Tom",
    "v": "Vincent",
    "V": "Vincent",
    "z": "Zen",
    "Z": "Zen",
    "man": "Man",
    "woman": "Woman",
    "bus": "Bus"

}

gos_voices = {
    "": "Narrator",
    "Liam": "Liam",
    "Cynthia": "Cynthia",
    "Cynthius": "Cynthia",
    "Trevor": "Trevor",
    "Oscar": "Oscar",
    "Brian": "Brian",
    "Ethan": "Ethan",
    "Marcus": "Marcus",
    "Calvin": "Calvin",
    "Henry": "Lumbard",
    "Nathan": "Nathan",
    "Marcus": "Marcus",
    "Customer": "Customer",
    "Receptionist": "Receptionist"
}

################################################################################

# Defines the games' dictionary
# The program expects the games' names to correlate
# with ElevenLabs voice entries:
# BEngel -> "BEngel: Chris"

# NOTE: These are WSL (/mnt/c/...) paths to the Windows checkout.
game_dict = {
    "Bound To College": {
        "main_lang": "English",
        "voices": btc_voices,
        "savepath": "/mnt/c/Users/olli_/Documents/GitHub/BoundToCollege/game",
    },
    "BEngel": {
        "main_lang": "German",
        "voices": bengel_voices,
        "savepath": "/mnt/c/Users/olli_/Documents/GitHub/B_Engel/game",
    },

    "GOS": {
        "main_lang": "English",
        "voices": gos_voices,
        "savepath": "/mnt/c/Users/olli_/Documents/GitHub/Gay-Office-Sim/game",
    }
}
