# Development Environment

## Supported Runtime

- Python 3.13 or 3.14
- Windows PowerShell for the documented local commands
- SQLite for local Template/MVP execution
- UTF-8 filesystem and console support

Install the reproducible direct dependency set:

```powershell
C:\Python314\python.exe -m pip install -r ai_agent_template\developer_kit\starter_kit\requirements.lock
```

Verify the active interpreter and package versions:

```powershell
C:\Python314\python.exe scripts\check_environment.py
```

`requirements.txt` remains the compatible-range declaration for SDK consumers. `requirements.lock` is the project validation baseline. A dependency upgrade must update the lock, run the complete quality gate, and record compatibility notes in this document.

The Codex sandbox may not inherit the Windows user site-packages directory. A package installed under `%APPDATA%\Python\Python314\site-packages` can therefore be available in the user's PowerShell session while conditional FastAPI tests remain skipped in the sandbox. The environment check must be run in the same terminal/interpreter used to start the application.
