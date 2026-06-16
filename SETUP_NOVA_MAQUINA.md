# JARVIS — Setup em Nova Maquina

## Pre-requisitos

```powershell
winget install Python.Python.3.11
winget install Git.Git
winget install Ollama.Ollama
```

Reabrir o PowerShell depois de instalar.

## 1. Clonar

```powershell
cd C:\Users\cibernetico
git clone https://github.com/luizfernandoantonio345-webs/JARVIS.git
cd JARVIS
```

## 2. Ambiente Python

```powershell
py -3.11 -m venv venv311
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\venv311\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
```

> Instalacao pode demorar 5-15 minutos dependendo da conexao.

## 3. Ollama + Modelo

```powershell
$env:OLLAMA_HOST = "127.0.0.1:11434"
Start-Process ollama -ArgumentList "serve" -WindowStyle Minimized
Start-Sleep 5
ollama pull mistral:7b
ollama pull llama3.2:3b
```

> `mistral:7b` tem ~4GB. Use `phi:latest` (~1.6GB) se quiser algo mais leve:
> `ollama pull phi`

## 4. Configuracao

```powershell
Copy-Item .env.example .env
```

Editar `.env` se necessario (trocar modelo, configurar voz, etc).

## 5. Iniciar

```powershell
.\start_jarvis.bat
```

O script cuida de tudo: ativa o venv, inicia o Ollama se necessario, sobe o backend e abre o browser.

## 6. Validar

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Ou abrir http://localhost:8000 no browser.

## Problemas Comuns

| Erro | Solucao |
|---|---|
| "Ollama connection refused" | Rodar `ollama serve` em outro terminal |
| "Module not found" | Confirmar venv311 ativo: `.\venv311\Scripts\Activate.ps1`, reinstalar: `pip install -r backend\requirements.txt` |
| "Port 8000 in use" | `netstat -ano \| findstr :8000` e `taskkill /PID [n] /F` |
| "python nao reconhecido" | Instalar Python 3.11 via winget ou python.org, reiniciar terminal |
| Script blocks por policy | `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| Modelo nao encontrado | `ollama list` para ver modelos disponiveis, ajustar JARVIS_MODEL no .env |
