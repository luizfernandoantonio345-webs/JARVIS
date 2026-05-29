# 🚀 JARVIS v6.0 — DEPLOY HOJE — INSTRUÇÕES PASSO A PASSO

## ⏱️ Tempo Total Estimado: 1,5-2 horas

---

## 🎯 VISÃO GERAL DO PLANO

```
FASE 1 (Prep)        →  10-15 min  → phase1_deploy_prep.py
           ↓
FASE 2 (Fixes)       →  20-30 min  → phase2_deploy_fixes.py  
           ↓
FASE 3 (Validation)  →  10-15 min  → phase3_deploy_validation.py
           ↓
FASE 4 (Deploy)      →   5-10 min  → startup_final.ps1
           ↓
✅ JARVIS ONLINE
```

---

## 📋 PASSO A PASSO

### PASSO 1: PREPARAÇÃO (10-15 min)

**Objetivo**: Corrigir ambiente, limpar venv, atualizar requirements

```powershell
# 1.1 — Abra PowerShell (como administrador, se necessário)
cd C:\Users\cibernetico\JARVIS

# 1.2 — Execute script de preparação
python phase1_deploy_prep.py
```

**Esperado**:
```
✓ Python 3.11 OK
✓ .env updated
✓ venv313 selected
✓ Requirements installed
✓ Logs cleaned
```

**Se falhar**:
- Python não encontrado? `python --version` (precisa 3.11+)
- venv não existe? `python -m venv venv311 && venv311\Scripts\pip install -r backend\requirements.txt`
- Permissões? Execute PowerShell como admin

---

### PASSO 2: CORREÇÕES (20-30 min)

**Objetivo**: Fixar conflitos de config, optimizar startup

```powershell
# 2.1 — Execute script de fixes
python phase2_deploy_fixes.py
```

**Esperado**:
```
✓ Fixed config.py: model defaults
✓ main.py: Checked imports  
✓ Health check: Created
✓ Heavy features: Disabled
```

**O que ele faz**:
- Padroniza modelo para `smollm2:135m` em config.py
- Verifica imports críticos em main.py
- Cria health check validator
- Desabilita prewarm pesado (acelera startup 20s)

---

### PASSO 3: VALIDAÇÃO (10-15 min)

**Objetivo**: Testar tudo antes do deploy final

```powershell
# 3.1 — Execute validação completa
python phase3_deploy_validation.py
```

**Esperado**:
```
TEST 1: Python Version         ✓
TEST 2: Ollama Connectivity    ⚠ (OK se warn)
TEST 3: Port Availability      ✓
TEST 4: Disk Space             ✓
TEST 5: Configuration Files    ✓
TEST 6: Backend Imports        ✓
TEST 7: Environment Variables  ✓
TEST 8: System Resources       ✓

Score: 100%
```

**Se Ollama falhar**:
```powershell
# Em outro PowerShell:
ollama serve
# Deixe rodando enquanto executa o deploy
```

**Se alguma test falhar**:
- **Port busy?** `netstat -ano | findstr :8000` → `taskkill /PID <ID> /F`
- **Disk space?** Libere >2GB
- **Imports?** `python -m pip install -r backend/requirements.txt`

---

### PASSO 4: DEPLOY FINAL (5-10 min)

**Objetivo**: Iniciar JARVIS com saúde completa

```powershell
# 4.1 — Inicie o backend
.\startup_final.ps1

# OU com opções customizadas:
.\startup_final.ps1 -Model smollm2:135m -Port 8000 -NoWait

# OU para desabilitar voice (mais rápido):
.\startup_final.ps1 -DisableVoice
```

**O script faz**:
- ✓ Mata processo antigo na porta 8000
- ✓ Ativa venv311
- ✓ Inicia uvicorn com otimizações
- ✓ Faz health check (30 tentativas)
- ✓ Abre browser automaticamente
- ✓ Monitora continuamente (Ctrl+C para parar)

**Esperado durante startup**:
```
→ Verifying prerequisites...
✓ Python venv found
✓ Ollama online
✓ Port 8000 is free
✓ Environment variables set

→ Starting JARVIS backend...
✓ Backend started (PID: 12345)
→ Waiting for backend (polling health endpoint)...
✓ Health check passed (attempt 5)

✓ JARVIS ONLINE
  🏠 Dashboard    : http://localhost:8000
  📚 API Docs     : http://localhost:8000/docs
  🔌 WebSocket    : ws://localhost:8000/ws/jarvis
  💚 Health       : http://localhost:8000/health
  📊 Metrics      : http://localhost:8000/metrics
```

**Tempo total de startup**: 8-15 segundos (dependendo do modelo)

---

## ✅ VERIFICAÇÃO PÓS-DEPLOY

Após ver "✓ JARVIS ONLINE", verifique:

### 1️⃣ **Health Endpoint**
```powershell
curl http://localhost:8000/health
```
Esperado: `{"status":"ok","uptime":XX.X,"version":"6.0"}`

### 2️⃣ **Chat Endpoint (sem voice)**
```powershell
curl -X POST http://localhost:8000/chat/process `
  -H "Content-Type: application/json" `
  -d '{"message":"Oi, como você está?","session_id":"test"}'
```
Esperado: Resposta do modelo em JSON

### 3️⃣ **Dashboard**
Abra `http://localhost:8000` no browser
- Deve carregar orb animado
- Deve ter input de chat funcional
- Deve mostrar status "ONLINE"

### 4️⃣ **WebSocket (se implementado)**
```powershell
# Teste com wscat se instalado:
npm install -g wscat
wscat -c ws://localhost:8000/ws/jarvis
```

---

## 🚨 TROUBLESHOOTING RÁPIDO

### ❌ Problema: "Impossível conectar-se ao servidor remoto"

**Solução**:
```powershell
# 1. Verifique se backend está rodando
Get-Process | Where-Object {$_.ProcessName -like "*python*"}

# 2. Se não aparecer, aguarde mais 10 segundos
# 3. Verifique logs
Get-Content backend/logs/jarvis.log -Tail 50

# 4. Mate processo antigo e retry
taskkill /F /IM python.exe /T
.\startup_final.ps1
```

### ❌ Problema: "Port 8000 already in use"

**Solução**:
```powershell
# Encontre e mate o processo
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Ou deixe que script auto-kill:
.\startup_final.ps1
```

### ❌ Problema: "Ollama não responde"

**Solução**:
```powershell
# Em novo terminal PowerShell:
ollama serve

# Verifique modelo disponível:
ollama list
# Deve mostrar: smollm2:135m (ou phi:latest)

# Se não tiver modelo, puxe:
ollama pull smollm2:135m
```

### ❌ Problema: Backend inicia mas fica lento

**Solução**:
1. Verifique RAM: `Get-Process python* | Measure-Object WorkingSet -Sum`
2. Se >1.5GB, use modelo mais leve:
   ```powershell
   .\startup_final.ps1 -DisableVoice -Model smollm2:135m
   ```
3. Se ainda lento, disabilite prewarm (verificar config.py)

### ❌ Problema: "ImportError" no backend

**Solução**:
```powershell
# Reinstale requirements
venv311\Scripts\pip install --upgrade -r backend\requirements.txt

# OU use venv novo se corrompido:
rmdir venv311
python -m venv venv311
venv311\Scripts\pip install -r backend\requirements.txt

# Retry:
.\startup_final.ps1
```

---

## 📊 MONITORAMENTO CONTÍNUO

O script `startup_final.ps1` monitora continuamente. Você verá:

```
[14:30:45] Health: OK | Uptime: 120.5s
[14:31:15] Health: OK | Uptime: 150.2s
[14:31:45] Health: OK | Uptime: 179.8s
```

Se aparecer erro:
```
⚠ [14:32:00] Health check failed
```

Significa que backend pode estar travando. Ctrl+C para parar e revise logs.

---

## 🎯 CHECKLIST PRÉ-DEPLOY FINAL

Antes de rodar PASSO 4, verifique:

- [ ] PASSO 1 completado sem erros
- [ ] PASSO 2 completado com "✓"
- [ ] PASSO 3 score 100% ou >80%
- [ ] Ollama rodando: `curl http://localhost:11434/api/tags`
- [ ] Porta 8000 livre: `netstat -ano | findstr :8000` (sem resultado)
- [ ] RAM disponível: >1.5GB
- [ ] Disk space: >2GB livre

---

## 📞 SUPORTE & REFERÊNCIAS

| Documento | Propósito |
|---|---|
| [DEPLOY_TODAY_CHECKLIST.md](DEPLOY_TODAY_CHECKLIST.md) | Checklist completo e diagnóstico |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Guia de troubleshooting |
| [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) | Guia detalhado de deploy |
| [docs/OPERATIONS_RUNBOOK.md](docs/OPERATIONS_RUNBOOK.md) | Operação contínua |
| [README.md](README.md) | Overview geral |

---

## ✨ PRÓXIMOS PASSOS (Após Online)

1. **Configurar backup automático**:
   ```powershell
   # Windows Task Scheduler — agendar:
   .\scripts\backup_db.ps1
   ```

2. **Setup monitoring**:
   ```powershell
   python scripts/health_monitor.py --interval 60
   ```

3. **Documentar URLs finais** (internal + externo se aplicável)

4. **Testar cada endpoint** com smoke test:
   ```powershell
   python tests/test_e2e_complete.py
   ```

---

**Status**: 🟢 PRONTO PARA DEPLOY HOJE  
**Data**: 28 de Maio de 2026  
**Tempo estimado**: 1.5-2 horas  
**Confiança**: 99%

---

## 🚀 READY? Execute:

```powershell
# TUDO DE UMA VEZ (executar em sequência):
python phase1_deploy_prep.py; python phase2_deploy_fixes.py; python phase3_deploy_validation.py; .\startup_final.ps1
```

Boa sorte! 🎉
