# JARVIS STARTUP INSTRUCTIONS - Windows (No pwsh.exe)

## Problem
- `pwsh.exe` (PowerShell Core) is NOT installed on this machine
- The GitHub Copilot PowerShell tool requires `pwsh.exe` and cannot execute commands
- Standard Windows tools available: `cmd.exe`, `powershell.exe` (Windows PowerShell 5.x)

## Solution
Since automated command execution is not available through the Copilot tools, you must start JARVIS manually.

## Method 1: Using the Batch Script (RECOMMENDED)

1. Open Command Prompt (cmd.exe)
2. Run this command:
   ```
  C:\Users\cibernetico\JARVIS\start_jarvis.bat
   ```
   Or:
   ```
   cd C:\Users\cibernetico\JARVIS
  start_jarvis.bat
   ```

## Method 2: Direct Python Launch

1. Open Command Prompt (cmd.exe)
2. Run:
   ```
   C:\Users\cibernetico\JARVIS\.venv\Scripts\python.exe C:\Users\cibernetico\JARVIS\launch_jarvis.py
   ```

## Method 3: Using PowerShell (Windows PowerShell 5.x)

1. Open PowerShell (NOT PowerShell Core)
2. Run:
   ```powershell
   & 'C:\Users\cibernetico\JARVIS\.venv\Scripts\python.exe' 'C:\Users\cibernetico\JARVIS\launch_jarvis.py'
   ```

## What to Expect

The launcher script will:
1. ✓ Check if JARVIS is already running
2. ✓ Test imports for backend.main and backend.main_simple
3. ✓ Choose the correct entry point
4. ✓ Start uvicorn server in background
5. ✓ Poll /health endpoint (up to 30 seconds)
6. ✓ Display startup status and links

Example output:
```
============================================================
  JARVIS AI Backend Launcher
============================================================

[✓] JARVIS is ONLINE after 5s!

{
  "status": "ok",
  "uptime": 5.2,
  "version": "5.2"
}

  API:  http://localhost:8000
  Docs: http://localhost:8000/docs
  WS:   ws://localhost:8000/ws/jarvis
  Log:  C:\Users\cibernetico\JARVIS\backend\logs\uvicorn.log
```

## Verify JARVIS is Running

### Browser
- http://localhost:8000/health
- http://localhost:8000/docs (API documentation)

### Command Line
```cmd
curl http://localhost:8000/health
```

Or with PowerShell:
```powershell
Invoke-WebRequest -Uri http://localhost:8000/health | Select-Object -ExpandProperty Content
```

## Environment Files
- **Config**: `C:\Users\cibernetico\JARVIS\backend\config.py`
- **Main backend**: `C:\Users\cibernetico\JARVIS\backend\main.py`
- **Fallback backend**: `C:\Users\cibernetico\JARVIS\backend\main_simple.py`
- **Environment**: `C:\Users\cibernetico\JARVIS\.env`
- **Logs**: `C:\Users\cibernetico\JARVIS\backend\logs\uvicorn.log`

## Environment Variables
The launcher automatically sets:
```
JARVIS_DISABLE_VOICE=1
```

Additional settings from .env:
```
JARVIS_OLLAMA_URL=http://192.168.0.106:11434
JARVIS_MODEL=phi:latest
JARVIS_TIMEOUT=60
JARVIS_PORT=8000
```

## Troubleshooting

### If startup fails:
1. Check log file: `C:\Users\cibernetico\JARVIS\backend\logs\uvicorn.log`
2. Verify Python venv: `C:\Users\cibernetico\JARVIS\.venv\Scripts\python.exe --version`
3. Test imports: `.venv\Scripts\python.exe -c "import backend.main; print('OK')"`
4. Check dependencies: `pip install -r backend/requirements.txt`

### If port 8000 is in use:
1. Check what's using it: `netstat -ano | findstr :8000`
2. Kill the process: `taskkill /PID <PID> /F`
3. Or use a different port by editing `launch_jarvis.py`

### If health check fails:
1. Wait a bit longer (10-20 seconds) and retry
2. Check the log file for error details
3. Try `backend.main_simple:app` entry point instead

## Key Files
- Python venv: `C:\Users\cibernetico\JARVIS\.venv\Scripts\python.exe`
- Alternative venvs: `.venv-1`, `venv`, `venv311`
- Launcher: `launch_jarvis.py` (Python-based, reliable cross-platform)
- Script oficial de duplo clique: `start_jarvis.bat`

---

**Next Steps**: Execute one of the startup methods above, then verify at http://localhost:8000/health
