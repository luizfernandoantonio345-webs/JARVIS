# TODO — Neural Core Chat and Docs (execução guiada)

- [x] 1) Auditar estado atual dos arquivos-chave (`backend/main.py`, `backend/routes/jarvis.py`, `frontend/jarvis_neural_core.html`, `backend/voice_v2/output.py`, `frontend/jarvis-dashboard.html`)
- [x] 2) Evoluir `backend/routes/jarvis.py` para contrato multimodal expandido em `POST /jarvis/ask` com metadados de anexos e TTS opcional
- [ ] 3) Implementar fluxo de geração/download de documento no backend e retorno como artefato no chat
- [ ] 4) Refatorar `frontend/jarvis_neural_core.html` para renderizar artefatos (resumo, tipo, páginas, preview e ações)
- [ ] 5) Integrar ações de voz (ler resumo/ler completo) e comandos de interface (“abrir chat”, “analisar documento”, “gerar documento”)
- [ ] 6) Fundir/aposentar `frontend/jarvis-dashboard.html` para manter Neural Core como frontend oficial único
- [ ] 7) Validar fluxo fim a fim: texto simples, PDF, DOCX/imagem, TTS e download de documento gerado
