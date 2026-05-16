"""Agente de desenvolvimento: cria projetos completos."""

import json
import subprocess
import sys
from pathlib import Path

import httpx

from backend.config import get_config


def _ask_ollama(prompt: str) -> str:
    cfg = get_config()
    try:
        resp = httpx.post(
            f"{cfg.ollama_url}/api/generate",
            json={"model": cfg.model, "prompt": prompt, "stream": False},
            timeout=60,
        )
        return resp.json().get("response", "")
    except Exception as e:
        return f"Erro Ollama: {e}"


def dev_agent(parameters: dict, player=None, speak=None) -> str:
    description = parameters.get("description", "")
    language = parameters.get("language", "python")
    project_name = parameters.get("project_name", "projeto_jarvis")

    if not description:
        return "Descricao do projeto e obrigatoria"

    project_dir = Path.home() / "Desktop" / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    if player:
        player.write_log(f"DevAgent: Criando projeto '{project_name}'...")

    # Pede ao Ollama para gerar o codigo
    prompt = f"""Crie um projeto {language} completo para: {description}

Responda APENAS com JSON neste formato:
{{
  "files": [
    {{"name": "main.py", "content": "# codigo aqui"}}
  ],
  "install": ["requests"],
  "run_command": "python main.py"
}}"""

    response = _ask_ollama(prompt)

    try:
        # Tenta extrair JSON da resposta
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(response[start:end])
        else:
            raise ValueError("JSON nao encontrado")

        # Cria os arquivos
        for file_info in data.get("files", []):
            file_path = project_dir / file_info["name"]
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(file_info["content"], encoding="utf-8")
            if player:
                player.write_log(f"DevAgent: Criado {file_info['name']}")

        # Instala dependencias
        deps = data.get("install", [])
        if deps:
            pip = sys.executable.replace("python.exe", "pip.exe")
            subprocess.run([pip, "install"] + deps, capture_output=True)

        # Abre no VSCode se disponivel
        try:
            subprocess.Popen(["code", str(project_dir)], shell=True)
        except Exception:
            pass

        return (
            f"Projeto '{project_name}' criado em {project_dir} "
            f"com {len(data.get('files', []))} arquivos. "
            f"Execute: {data.get('run_command', 'python main.py')}"
        )

    except Exception as e:
        # Fallback: cria arquivo basico
        main_file = project_dir / "main.py"
        main_file.write_text(
            f"# {description}\n# Projeto gerado pelo JARVIS\n\nprint('Hello from JARVIS!')\n"
        )
        return f"Projeto basico criado em {project_dir}. Erro no parser: {e}"
