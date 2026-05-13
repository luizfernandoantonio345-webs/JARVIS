import subprocess
proc = subprocess.Popen(
    [r'c:\Users\cibernetico\JARVIS\.venv\Scripts\python.exe', '-m', 'uvicorn', 'backend.main:app', '--host', '0.0.0.0', '--port', '8000'],
    cwd=r'c:\Users\cibernetico\JARVIS',
    stdout=open(r'c:\Users\cibernetico\JARVIS\server_out.log', 'w'),
    stderr=subprocess.STDOUT,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
)
print(f"Started with PID: {proc.pid}")
