@echo off

REM If a local secrets helper exists, load it and then run.
if exist "set_env.ps1" (
	powershell -NoProfile -ExecutionPolicy Bypass -Command "& { . '.\\set_env.ps1'; python '.\\language.py' @args }" --% %*
) else (
	python language.py %*
)
pause