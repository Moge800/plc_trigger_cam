# PLC Trigger Camera — startup script for Windows PowerShell
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

# Sync dependencies (creates .venv if needed)
uv sync

# Launch application
uv run src/main.py @args
