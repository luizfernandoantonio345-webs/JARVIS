# 🤖 JARVIS v6.0 — GUIA COMPLETO DE USO

## 🚀 INICIAR O SISTEMA

```powershell
cd C:\Users\cibernetico\JARVIS
start_jarvis.bat
```

→ Aguarde 6 segundos  
→ Browser abre em **http://localhost:8000**  
→ Verá a interface com o **orbe animado** no centro

---

## 📝 COMO INTERAGIR COM JARVIS

### **1. VIA VOZ (Speech Recognition)**

- **Pressione `ESPAÇO`** → o sistema fica em escuta
- **Fale naturalmente** → transcrição aparece no campo de comando
- **Após falar** → resposta é processada automaticamente

**Exemplos:**
```
oi jarvis
→ Orbe pisca + resposta animada + áudio em português

como está?
→ Simula conversa natural

qual é a data de hoje?
→ Responde e fala a resposta
```

### **2. VIA TECLADO**

- **Pressione `ESPAÇO`** → abre campo de entrada
- **Digite sua pergunta**
- **Pressione `ENTER`** → envia para processar

---

## 🎮 CONTROLES PRINCIPAIS

| Tecla | Função |
|-------|--------|
| **ESPAÇO** | Abre/fecha campo de comando |
| **ENTER** | Envia comando quando campo está aberto |
| **ESC** | Fecha widgets + reseta interface |
| **1** | Mostra/oculta widget: "ARQUIVO: NÚCLEO DO SISTEMA" |
| **2** | Mostra/oculta widget: "RELATÓRIO: ANOMALIAS GLOBAIS" |
| **3** | Mostra/oculta widget: "ANÁLISE DE FLUXO DE DADOS" |
| **4** | Mostra/oculta widget: "PROTOCOLOS ATIVOS" |
| **0** | Fecha tudo |
| **A** | Ativa/desativa modo ALERTA (visual vermelho) |

---

## 💬 EXEMPLOS DE COMANDOS

### **Modo Visual**
```
mostrar código
→ Abre widget com arquivo do sistema

mostrar mapa
→ Mostra anomalias globais

mostrar dados
→ Exibe CPU, RAM, Rede em tempo real

mostrar protocolos
→ Lista protocolos ativos

mostrar tudo
→ Abre todos os 4 widgets

fechar
→ Fecha tudo e reseta
```

### **Modo Perguntas**
```
oi jarvis
→ Resposta geral

escreva hello world em python
→ JARVIS gera código Python

abrir chrome
→ Executa ações do sistema (se configurado)

qual é seu propósito?
→ Responde sobre sua função

crie um relatório sobre segurança
→ Gera documento (salvo em temp)
```

---

## 📡 WEBSOCKET (Browser Console)

Teste conexão direta no **F12 → Console**:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/jarvis');

ws.onopen = () => {
  console.log('✓ Conectado!');
  ws.send('oi jarvis');
};

ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if(m.type === 'token') console.log(m.content);
  if(m.type === 'done') console.log('[RESPOSTA COMPLETA]');
};

ws.onerror = () => console.log('✗ Erro conexão');
```

---

## 🔧 ENDPOINTS HTTP (Backend)

### **1. /ask (POST)**
Envia pergunta com suporte a áudio e anexos

```bash
curl -X POST http://localhost:8000/jarvis/ask \
  -F "text=oi jarvis" \
  -F "tts=true" \
  -F "tts_summary_only=true"
```

**Resposta:**
```json
{
  "status": "ok",
  "response": "Olá! Estou aqui para ajudar.",
  "domain_used": "general",
  "memory_augmented": true,
  "sources": [],
  "tts_audio_url": "/jarvis/tts?path=..."
}
```

### **2. /tts (GET)**
Gera áudio a partir de texto

```bash
curl "http://localhost:8000/jarvis/tts?text=olá&lang=pt"
```

→ Retorna arquivo MP3

### **3. /generate-document (POST)**
Cria documento (txt/md/json)

```bash
curl -X POST http://localhost:8000/jarvis/generate-document \
  -F "content=Relatório de segurança..." \
  -F "title=relatorio_seguranca" \
  -F "extension=md"
```

---

## 📊 RECURSOS PRINCIPAIS

### **1. Análise de Domínio**
JARVIS detecta automaticamente o domínio da pergunta:
- `cybersecurity` → especialista em segurança
- `code` → especialista em programação
- `general` → assistente geral

### **2. Memória Contextual**
- Armazena histórico de interações
- Reconhece padrões de perguntas
- Melhora respostas com experiência

### **3. Processamento de Documentos**
- Upload de PDFs/documentos
- Análise automática
- Integração com resposta

### **4. Geração de Documentos**
- Cria relatórios em Markdown
- Exporta análises em JSON
- Salva em texto puro

---

## 🎯 FLUXO PADRÃO

```
1. Pressiona ESPAÇO ou fala
   ↓
2. JARVIS processa via WebSocket
   ↓
3. Orbe anima e mostra "Processando..."
   ↓
4. Domínio é detectado
   ↓
5. Especialista relevante responde
   ↓
6. Resposta stream em tempo real
   ↓
7. TTS fala a resposta
   ↓
8. Volta ao modo aguardando
```

---

## ⚙️ CONFIGURAÇÕES

### **Audio**
- Reconhecimento em português (pt-BR)
- TTS em português ou inglês
- Frequência de captura: 150-3500 Hz

### **Visual**
- **Orbe azul**: ativo/processando
- **Orbe dourado**: intensa atividade
- **Orbe vermelho**: modo alerta
- **Widgets**: 4 painéis informativos

### **Performance**
- **CPU**: 74% (indicador W2)
- **RAM**: 61% (indicador W2)
- **REDE**: 32% (indicador W2)

---

## 🐛 TROUBLESHOOTING

| Problema | Solução |
|----------|---------|
| Sem som | Verifique permissão de microfone + browser suporta Web Audio |
| WebSocket não conecta | Backend pode estar offline → reinicie com `start_jarvis.bat` |
| Voz não funciona | Chrome/Edge requeridos. Firefox tem suporte limitado |
| Sem respostas | Verifique `http://localhost:8000/health` |
| Teclado não responde | Clique na interface primeiro, depois aperte ESPAÇO |

---

## 💡 DICAS PRÁTICAS

1. **Para conversa natural**: Use fala, é mais rápido
2. **Para código**: Digite ou dite explicitamente "escreva X em Python"
3. **Para análise**: Diga "mostrar tudo" antes para visualizar widgets
4. **Para documentos**: Use "crie um relatório sobre..." e depois downloads em temp
5. **Para teste rápido**: F12 → Console → rode o WebSocket direto

---

## 📞 STATUS DO SISTEMA

- **Versão**: 6.0 (Production)
- **Backend**: FastAPI + Ollama remoto (PC2)
- **Frontend**: Vite + Canvas HTML5
- **BD Memória**: Chroma Vector Store
- **Audio**: Web Speech API + Edge TTS/Ollama

**Última atualização**: 17 de maio de 2026 ✓

---

Pronto para usar! 🚀
