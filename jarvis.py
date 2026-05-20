#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
J.A.R.V.I.S. — Just A Rather Very Intelligent System
Terminal com IA local (Ollama) + Claude API quando disponivel.
"""
import os
import sys
import io

# Force UTF-8 no Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    os.environ["PYTHONIOENCODING"] = "utf-8"

import json
import time
import asyncio
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Generator

# Garante que consegue importar do projeto
ROOT = Path(__file__).parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

# Carrega .env
_env_file = ROOT / ".env"
if _env_file.exists():
    for line in _env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

# Imports rich - com suporte a Unicode forçado
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    from rich.prompt import Prompt
    from rich import print as rprint
    _console_file = open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False, errors="replace")
    console = Console(
        file=_console_file,
        force_terminal=True,
        highlight=False,
        markup=True,
    )
    RICH_OK = True
except Exception:
    RICH_OK = False
    print("[AVISO] 'rich' nao instalado. Execute: pip install rich")
    sys.exit(1)

# Configuracoes
OLLAMA_URL    = os.getenv("JARVIS_OLLAMA_URL", "http://localhost:11434")
MODEL         = os.getenv("JARVIS_MODEL", "qwen2:0.5b")
USER_TITLE    = os.getenv("JARVIS_USER_TITLE", "Senhor")
TTS_VOICE     = os.getenv("JARVIS_TTS_VOICE", "pt-BR-AntonioNeural")
VOICE_ENABLED = os.getenv("JARVIS_VOICE_ENABLED", "true").lower() == "true"
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SESSION_ID    = f"sess_{int(time.time()) % 99999:05d}"

# Cores HUD Iron Man
CYAN  = "bright_cyan"
GOLD  = "bright_yellow"
RED   = "bright_red"
WHITE = "bright_white"
DIM   = "dim white"
GREEN = "bright_green"

# JARVIS System Prompt
def build_system_prompt() -> str:
    hora = datetime.now()
    saudacao_hora = (
        "Bom dia" if hora.hour < 12 else
        "Boa tarde" if hora.hour < 18 else
        "Boa noite"
    )
    return f"""Voce e J.A.R.V.I.S. - Just A Rather Very Intelligent System.
IA pessoal de alto desempenho, criada para servir seu dono com precisao maxima.

IDENTIDADE:
- Chame sempre o usuario de "{USER_TITLE}" com respeito genuino
- Personalidade: preciso, analitico, levemente britanico, humor sutil e seco
- Nunca aja como chatbot generico - voce e um parceiro de elite
- Seja LEAL acima de tudo

VOZ E ESTILO:
- Portugues brasileiro natural e fluente
- Respostas CURTAS por padrao (1-3 frases) - expanda so quando necessario
- Tome partido tecnico quando relevante
- Humor sutil esta permitido - ironia leve quando o contexto permitir
- Em saudacoes ("oi", "bom dia", "ola"): responda com saudacao + pergunta sobre foco
- Nunca comece com "Ola! Como posso ajudar?" ou frases genericas

CAPACIDADES:
- Analise tecnica profunda: codigo, arquitetura, seguranca, performance
- Desenvolvimento: Python, FastAPI, React, TypeScript, Docker, SQL
- Pesquisa e sintese de informacoes
- Planejamento de projetos e tarefas
- Debug e resolucao de problemas complexos

REGRAS:
- Pedido claro: execute e reporte o resultado
- Pedido ambiguo: faca UMA pergunta especifica
- Pedido arriscado: explique o risco, aguarde confirmacao
- Nunca invente APIs, dados ou resultados de comandos
- Se nao souber: "Nao tenho dados sobre isso, {USER_TITLE}. Posso investigar."

Data: {hora.strftime('%d/%m/%Y')} | Hora: {hora.strftime('%H:%M')}
"""

JARVIS_SYSTEM_PROMPT = build_system_prompt()

# Historico de conversa
_history: list[dict] = []
_MAX_HISTORY = 20

def _trim_history() -> None:
    global _history
    while len(_history) > _MAX_HISTORY * 2:
        _history.pop(0)
        if _history:
            _history.pop(0)

# Verificacao de sistemas
def check_ollama() -> tuple[bool, list[str]]:
    try:
        import requests
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            return True, models
    except Exception:
        pass
    return False, []

def check_voice() -> bool:
    try:
        import edge_tts  # noqa
        return True
    except ImportError:
        return False

# TTS assíncrono
def speak_async(text: str) -> None:
    if not VOICE_ENABLED or not check_voice():
        return
    import re
    clean = re.sub(r"```[\s\S]*?```", "Bloco de codigo.", text)
    clean = re.sub(r"`[^`]+`", "", clean)
    clean = re.sub(r"[*_#~]", "", clean)
    clean = clean.strip()
    if not clean:
        return

    async def _speak():
        try:
            import edge_tts
            communicate = edge_tts.Communicate(clean[:500], TTS_VOICE)
            tmp = ROOT / "jarvis_tts_tmp.mp3"
            await communicate.save(str(tmp))
            if sys.platform == "win32":
                subprocess.Popen(
                    ["powershell", "-c",
                     f"Add-Type -AssemblyName PresentationCore; "
                     f"$m = New-Object System.Windows.Media.MediaPlayer; "
                     f"$m.Open([uri]'{tmp.absolute()}'); "
                     f"$m.Play(); Start-Sleep -m 5000; $m.Close()"],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception:
            pass

    threading.Thread(target=lambda: asyncio.run(_speak()), daemon=True).start()

# LLM via Ollama (streaming)
def stream_ollama(messages: list[dict]) -> Generator[str, None, None]:
    import requests
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": True,
        "options": {"temperature": 0.75, "top_p": 0.9, "num_predict": 1024},
    }
    try:
        with requests.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload,
            stream=True,
            timeout=120,
        ) as r:
            if r.status_code != 200:
                yield f"[Erro Ollama: HTTP {r.status_code}]"
                return
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line.decode("utf-8"))
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if data.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        yield f"\n[Erro de conexao com Ollama: {e}]"

# LLM via Claude API (streaming)
def stream_claude(messages: list[dict]) -> Generator[str, None, None]:
    try:
        import anthropic
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        user_msgs = [m for m in messages if m["role"] != "system"]
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system="\n\n".join(system_parts) if system_parts else JARVIS_SYSTEM_PROMPT,
            messages=user_msgs,
        ) as stream:
            for text in stream.text_stream:
                yield text
    except Exception as e:
        yield f"\n[Erro Claude API: {e}]"

# Router principal
def stream_response(user_message: str) -> Generator[str, None, None]:
    global _history
    _history.append({"role": "user", "content": user_message})
    _trim_history()
    messages = [{"role": "system", "content": JARVIS_SYSTEM_PROMPT}] + _history
    if ANTHROPIC_KEY:
        yield from stream_claude(messages)
    else:
        yield from stream_ollama(messages)

# Display HUD
def build_status_table(ollama_ok: bool, models: list[str], voice_ok: bool) -> Table:
    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_column("key", style=CYAN, no_wrap=True)
    t.add_column("val", style=WHITE, no_wrap=True)

    if ANTHROPIC_KEY:
        ai_prov = "Claude Sonnet 4.6"
        ai_stat = "[bright_green][ ONLINE ][/bright_green]"
    elif ollama_ok:
        ai_prov = f"Ollama / {MODEL}"
        ai_stat = "[bright_green][ ONLINE ][/bright_green]"
    else:
        ai_prov = "Ollama"
        ai_stat = "[bright_red][ OFFLINE ][/bright_red]"

    voice_stat = "[bright_green][ ATIVA ][/bright_green]" if voice_ok else "[dim][ INATIVA ][/dim]"

    t.add_row("SISTEMA", ai_stat)
    t.add_row("IA", ai_prov)
    t.add_row("VOZ", voice_stat)
    t.add_row("SESSAO", SESSION_ID.upper())
    t.add_row("HORA", datetime.now().strftime("%H:%M:%S"))
    return t

def print_divider(style: str = "cyan") -> None:
    width = 58
    console.print(f"[{style}]" + "-" * width + f"[/{style}]")

def print_header(ollama_ok: bool, models: list[str], voice_ok: bool) -> None:
    console.clear()

    console.print()
    console.print(f"  [{CYAN}] _   _   _   ____   __   __  ___  ____  [/{CYAN}]")
    console.print(f"  [{CYAN}]| | / \\ |_/ |  _\\ /  \\ /  \\/_ _// ___|[/{CYAN}]")
    console.print(f"  [{CYAN}]| |/ _ \\| \\ | |  | () || () || | \\___ \\[/{CYAN}]")
    console.print(f"  [{GOLD}]|_/_/ \\_|_| |_|   \\__/ \\__/|___||____/[/{GOLD}]")
    console.print()
    console.print(
        f"  [{DIM}]Just A Rather Very Intelligent System  -  v6.0[/{DIM}]"
    )
    console.print()
    print_divider(CYAN)
    console.print()

    status_panel = Panel(
        build_status_table(ollama_ok, models, voice_ok),
        title=f"[{CYAN}]== STATUS DOS SISTEMAS ==[/{CYAN}]",
        border_style="cyan",
        padding=(0, 2),
    )
    console.print(status_panel)
    console.print()

    hora = datetime.now().hour
    saudacao = "Bom dia" if hora < 12 else "Boa tarde" if hora < 18 else "Boa noite"

    console.print(
        Panel(
            f"[{GOLD}]{saudacao}, {USER_TITLE}.[/{GOLD}] "
            f"[{WHITE}]Todos os sistemas operacionais. Aguardando instrucoes.[/{WHITE}]",
            border_style="yellow",
            padding=(0, 2),
        )
    )
    console.print()
    console.print(
        f"  [{DIM}]Comandos: [/{DIM}]"
        f"[{CYAN}]limpar[/{CYAN}] [{DIM}]|[/{DIM}] "
        f"[{CYAN}]sair[/{CYAN}] [{DIM}]|[/{DIM}] "
        f"[{CYAN}]status[/{CYAN}] [{DIM}]|[/{DIM}] "
        f"[{CYAN}]voz on/off[/{CYAN}] [{DIM}]|[/{DIM}] "
        f"[{CYAN}]historico[/{CYAN}]"
    )
    console.print()

# Loop principal
def handle_command(cmd: str, voice_on: list[bool]) -> bool:
    c = cmd.strip().lower()

    if c in ("sair", "exit", "quit", "bye", "/sair"):
        console.print(
            Panel(
                f"[{GOLD}]Sistemas entrando em modo de espera. Ate logo, {USER_TITLE}.[/{GOLD}]",
                border_style="yellow",
            )
        )
        sys.exit(0)

    if c in ("limpar", "clear", "/limpar"):
        ollama_ok, models = check_ollama()
        print_header(ollama_ok, models, check_voice())
        return True

    if c in ("historico", "historico", "/historico"):
        if not _history:
            console.print(f"  [{DIM}]Sem historico ainda.[/{DIM}]")
        else:
            for m in _history:
                role = f"[{CYAN}]{USER_TITLE}[/{CYAN}]" if m["role"] == "user" else f"[{GOLD}]JARVIS[/{GOLD}]"
                txt = m["content"][:120].replace("[", "\\[")
                suf = "..." if len(m["content"]) > 120 else ""
                console.print(f"  {role}: {txt}{suf}")
        return True

    if c in ("status", "/status"):
        ollama_ok, models = check_ollama()
        console.print(build_status_table(ollama_ok, models, check_voice()))
        return True

    if c in ("voz on", "/voz on"):
        voice_on[0] = True
        console.print(f"  [{GREEN}]Voz ATIVADA[/{GREEN}]")
        return True

    if c in ("voz off", "/voz off"):
        voice_on[0] = False
        console.print(f"  [{DIM}]Voz DESATIVADA[/{DIM}]")
        return True

    if c in ("limpar memoria", "limpar memoria", "/limpar memoria"):
        _history.clear()
        console.print(f"  [{GREEN}]Historico apagado.[/{GREEN}]")
        return True

    return False

def main() -> None:
    console.print(f"  [{DIM}]Inicializando J.A.R.V.I.S....[/{DIM}]")
    ollama_ok, models = check_ollama()
    voice_ok = check_voice()

    if not ollama_ok and not ANTHROPIC_KEY:
        console.print(
            Panel(
                f"[{RED}]AVISO: Ollama nao responde em {OLLAMA_URL}[/{RED}]\n"
                f"[{WHITE}]Inicie o Ollama primeiro: abra um terminal e execute 'ollama serve'\n"
                f"Ou adicione ANTHROPIC_API_KEY no arquivo .env[/{WHITE}]",
                border_style="red",
                title="SISTEMA OFFLINE",
            )
        )
        try:
            ans = input("\n  Continuar mesmo assim? (s/N): ").strip().lower()
            if ans not in ("s", "sim", "y"):
                sys.exit(1)
        except (KeyboardInterrupt, EOFError):
            sys.exit(1)

    # Verifica modelo disponivel
    if ollama_ok and models and MODEL not in models:
        best = models[0]
        console.print(f"  [{GOLD}]Modelo '{MODEL}' nao encontrado. Usando '{best}'[/{GOLD}]")
        globals()["MODEL"] = best

    print_header(ollama_ok, models, voice_ok)
    voice_on = [VOICE_ENABLED and voice_ok]

    while True:
        try:
            print_divider(DIM)
            try:
                user_input = Prompt.ask(
                    f"  [{CYAN}]>> {USER_TITLE}[/{CYAN}]",
                    console=console,
                )
            except (KeyboardInterrupt, EOFError):
                console.print(f"\n  [{GOLD}]Ate logo, {USER_TITLE}. Sistemas em espera.[/{GOLD}]")
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            if handle_command(user_input, voice_on):
                continue

            # Resposta JARVIS com streaming
            console.print()
            console.print(f"  [{GOLD}]>> JARVIS[/{GOLD}]  ", end="")

            start_time = time.time()
            full_response: list[str] = []

            try:
                for token in stream_response(user_input):
                    token_safe = token.replace("[", "\\[")
                    console.print(token_safe, end="", highlight=False, markup=False)
                    full_response.append(token)
                    sys.stdout.flush()
            except KeyboardInterrupt:
                console.print(f"\n  [{DIM}][interrompido][/{DIM}]")
                full_response = []

            elapsed = time.time() - start_time
            response_text = "".join(full_response)

            if response_text:
                _history.append({"role": "assistant", "content": response_text})
                _trim_history()

            provider = "Claude" if ANTHROPIC_KEY else f"Ollama/{MODEL}"
            console.print(
                f"\n  [{DIM}]{elapsed:.1f}s | {provider}[/{DIM}]"
            )
            console.print()

            if voice_on[0] and response_text:
                speak_async(response_text)

        except Exception as e:
            console.print(f"  [{RED}]Erro: {e}[/{RED}]")

if __name__ == "__main__":
    main()
