"""
Configuração global de testes para o JARVIS.
Define fixtures e marcadores compartilhados.
"""
import os
import sys

# Garante que o backend/ está no sys.path para todos os testes
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Variáveis de ambiente padrão para testes (evita carregar config real)
os.environ.setdefault("JARVIS_MODEL", "smollm2:135m")
os.environ.setdefault("JARVIS_VOICE_ENABLED", "false")
os.environ.setdefault("JARVIS_HEADSET_MODE", "false")
os.environ.setdefault("JARVIS_WAKE_WORD_ENABLED", "false")
os.environ.setdefault("JARVIS_LOG_LEVEL", "WARNING")
os.environ.setdefault("JARVIS_SECRET_KEY", "test_key_hex_only_for_testing_do_not_use_in_prod")
