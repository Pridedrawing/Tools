param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptDirWin = (Resolve-Path $scriptDir).Path

# Translate Windows path to a WSL path using wslpath.
$wslScriptDir = (wsl.exe -e wslpath -a "$scriptDirWin") -replace "\r?\n$", ""

# Use Ubuntu (default distro). After reboot/Ubuntu install, this should work.
# You still need a working Python + deps inside WSL.
$bash = @(
    "cd '$wslScriptDir'",
    "export VOICEOVER_CONFIG=config_wsl",
    "if [ -x /home/olli_/.venvs/voiceover311/bin/python ]; then /home/olli_/.venvs/voiceover311/bin/python ./gen.py ${Args}; elif [ -x /home/olli_/.venvs/voiceover/bin/python ]; then /home/olli_/.venvs/voiceover/bin/python ./gen.py ${Args}; else python3 ./gen.py ${Args}; fi"
) -join "; "

wsl.exe -e bash -lc $bash
