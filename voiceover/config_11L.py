import os

game_name = "Bound To College"  # Corresponds to game name in 'game_dict' and ElevenLabs: "Bound To College", "BEngel", or "GOS"
lang = "English"  # Corresponds to 'game/tl/[lang]/'

################################################################################

# Defines the voices' dictionary
# Mind the trailing commas!
bengel_voices = {
    "a": "Alien",
    "b": "Ben",
    "c": "Chris",
    "d": "Ben",  # As the demonised version of himself
    "h": "Hartmann",
    "j": "Jeff",
    "k": "Kyle",
    "l": "Lucifer",
    "m": "Marvin",
    "md": "Marvin",
    "s": "Sabrina",
    "t": "Tim",
    "z": 0,  # Ignored
    "": "Narrator",
    "centered": "Narrator",
    "e_nvl": "Sabrina",  # Sabrina on the phone
    "n_nvl": "Jeff",  # Jeff on the phone
}

btc_voices = {
    "": ["Narrator", "Yko7PKHZNXotIFUBG7I9"],
    "a": "Administrator",
    "A": "Administrator",
    "c": "Connor",
    "C": "Connor",
    "h": ["Headmaster", "XB0fDUnXU5powFXDhCwa"],
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
    "v": "Vincent",
    "V": "Vincent",
    "z": "Zen",
    "Z": "Zen",
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
    "Receptionist": "Receptionist",
}

################################################################################

# Defines the games' dictionary
# The program expects the games' names to correlate
# with ElevenLabs voice entries:
# BEngel -> "BEngel: Chris"

game_dict = {
    "Bound To College": {
        "main_lang": "English",
        "voices": btc_voices,
        "savepath": "C:/Users/olli_/Documents/GitHub/BoundToCollege/game",
    },
    "BEngel": {
        "main_lang": "German",
        "voices": bengel_voices,
        "savepath": "C:/Users/olli_/Documents/GitHub/B_Engel/game",
    },
    "GOS": {
        "main_lang": "English",
        "voices": gos_voices,
        "savepath": "C:/Users/olli_/Documents/GitHub/Gay-Office-Sim/game",
    },
}

################################################################################

filename = "dialogue.csv"
delimiter = "\t"  #'\t' for tab

# Do NOT hardcode API keys in this repository.
# Set this in your shell instead, e.g. PowerShell:
#   $Env:ELEVENLABS_API_KEY = "..."
api_key = os.getenv("ELEVENLABS_API_KEY", "")
