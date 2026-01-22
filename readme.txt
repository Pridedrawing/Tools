README — Simple setup for API keys (no coding)
============================================

This folder contains tools that need an “API key” to talk to online services.

GOOD NEWS:
- You do NOT type the API key every time.
- You do NOT put the API key into the Python code.
- You store the key in a small local helper file that is NOT uploaded to GitHub.

We will use a helper file named:
- set_env.ps1

That helper file sets “environment variables” (think: secret settings) for the
current PowerShell window.


IMPORTANT SAFETY RULES (please read)
-----------------------------------
1) NEVER post your API key in Discord, email, screenshots, GitHub, etc.
2) NEVER commit the key to GitHub.
3) The real helper file is named set_env.ps1 and is ignored by git.
   (A safe example file set_env.ps1.example is allowed to exist in GitHub.)


EASIEST METHOD (recommended)
===========================

If you don’t want to deal with PowerShell commands at all:

1) Double-click: setup_keys.bat
2) Paste the key(s) when prompted
3) Press Enter to accept the defaults

After that you can just double-click:
- voiceover\run.bat
- Language Detection\run.bat


Part A — Voiceover tool (ElevenLabs)
===================================

You will set one key:
- ELEVENLABS_API_KEY

A1) Open PowerShell
-------------------
- Click Start
- Type: PowerShell
- Open “Windows PowerShell”

A2) Go to the voiceover folder
------------------------------
Copy and paste this line into PowerShell:

    cd "C:\Users\olli_\Documents\GitHub\Tools\voiceover"

(If you installed Tools somewhere else, the path may be different.)

A3) Create your personal helper file (one-time)
----------------------------------------------
We already provide a safe template file.
Now copy it to the real secrets file:

    copy .\set_env.ps1.example .\set_env.ps1

A4) Put your real key into set_env.ps1 (one-time)
------------------------------------------------
1) Open File Explorer
2) Go to: C:\Users\olli_\Documents\GitHub\Tools\voiceover
3) Right-click set_env.ps1
4) Choose “Edit” (or “Edit with Notepad”)
5) You will see something like:

    $Env:ELEVENLABS_API_KEY = "PASTE_YOUR_ELEVENLABS_KEY_HERE"

6) Replace PASTE_YOUR_ELEVENLABS_KEY_HERE with your real key.
7) Save the file and close Notepad.

A5) Load the helper into PowerShell (every new terminal)
--------------------------------------------------------
This is the magic line. Copy/paste it:

    . .\set_env.ps1

IMPORTANT:
- There is a DOT, then a SPACE, then .\set_env.ps1
- It must be exactly like that.

A6) Run the voiceover generator
------------------------------
Example (adjust parameters to what you use):

    python .\gen.py --help

Or your normal command:

    python .\gen.py --no-select --dialogue "C:\Users\olli_\Documents\GitHub\Tools\Missing Files\dialogue_missing.tab" --log "C:\Users\olli_\Documents\GitHub\Tools\voiceover\log.txt"


Part B — Language Detection tool (DeepL)
========================================

You will set one key:
- DEEPL_API_KEY

B1) Open PowerShell
-------------------
Same as above.

B2) Go to the Language Detection folder
--------------------------------------
Copy/paste:

    cd "C:\Users\olli_\Documents\GitHub\Tools\Language Detection"

B3) Create your helper file (one-time)
--------------------------------------

    copy .\set_env.ps1.example .\set_env.ps1

B4) Put your real key into set_env.ps1 (one-time)
------------------------------------------------
Edit set_env.ps1 and replace the placeholder:

    $Env:DEEPL_API_KEY = "PASTE_YOUR_DEEPL_KEY_HERE"

Save and close.

B5) Load the helper (every new terminal)
----------------------------------------

    . .\set_env.ps1

B6) Run the script
------------------

    python .\language.py


How to know it worked
====================

If the key is NOT set, the scripts will show a clear message like:
- “Error: ElevenLabs API key not configured. Set environment variable ELEVENLABS_API_KEY”
- or “DEEPL_API_KEY is not set…”

If the key IS set:
- voiceover/gen.py prints “API key set: yes”


Common mistakes & fixes
======================

1) “. .\set_env.ps1” does nothing / key still missing
-----------------------------------------------------
You probably typed it wrong.
It MUST be:

    . .\set_env.ps1

(Yes: dot + space + dot-backslash)

2) “python is not recognized”
-----------------------------
Python is not installed or not on PATH.
Install Python from python.org (or the Microsoft Store) and check “Add Python to PATH”.

3) You set the key but it still fails
-------------------------------------
Close PowerShell and open a NEW one, then run:

    cd "C:\Users\olli_\Documents\GitHub\Tools\voiceover"
    . .\set_env.ps1
    python .\gen.py --help

4) I’m scared I will upload my keys
-----------------------------------
Good! That’s healthy.
- The file set_env.ps1 is ignored by git and should not be committed.
- Do NOT paste keys into any .py files.
- Do NOT paste keys into messages/screenshots.


Alternative: Permanent Windows environment variables
===================================================

If you want Windows to remember keys automatically without running set_env.ps1:
- You can set user environment variables in Windows settings.
- But the helper method is often simpler and safer.


Where are the example templates?
===============================
- Tools\voiceover\set_env.ps1.example
- Tools\Language Detection\set_env.ps1.example

You copy each one to set_env.ps1 and fill in the real key.

END
