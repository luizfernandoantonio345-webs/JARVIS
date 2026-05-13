"""Escreve, edita, explica, roda e builda código"""
import subprocess
import sys
import httpx
from pathlib import Path

def _ask_ollama(prompt: str, model: str = "qwen2:0.5b") -> str:
    try:
        resp = httpx.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=60
        )
        return resp.json().get("response", "")
    except Exception as e:
        return f"Erro Ollama: {e}"

def code_helper(parameters: dict, player=None, speak=None) -> str:
    action = parameters.get("action", "auto")
    description = parameters.get("description", "")
    language = parameters.get("language", "python")
    output_path = parameters.get("output_path", "")
    file_path = parameters.get("file_path", "")
    code = parameters.get("code", "")
    args = parameters.get("args", "")
    timeout = parameters.get("timeout", 30)

    try:
        # Lê arquivo existente se fornecido
        existing_code = ""
        if file_path and Path(file_path).exists():
            existing_code = Path(file_path).read_text(encoding="utf-8")

        if action in ["explain", "auto"] and (existing_code or code):
            target_code = existing_code or code
            prompt = f"Explique este código {language} de forma clara e concisa em português:\n\n{target_code[:3000]}"
            explanation = _ask_ollama(prompt)
            if player:
                player.write_log(f"CodeHelper: {explanation[:200]}")
            if speak:
                speak(explanation[:500])
            return explanation

        elif action == "write":
            prompt = f"Escreva código {language} completo para: {description}\nResponda APENAS com o código, sem explicações."
            generated = _ask_ollama(prompt)
            
            # Remove markdown code blocks se houver
            if "```" in generated:
                lines = generated.split("\n")
                clean_lines = [l for l in lines if not l.startswith("```")]
                generated = "\n".join(clean_lines)
            
            save_path = output_path or f"jarvis_code.{_get_ext(language)}"
            Path(save_path).write_text(generated, encoding="utf-8")
            
            if player:
                player.write_log(f"CodeHelper: código salvo em {save_path}")
            return f"Código gerado e salvo em {save_path}"

        elif action == "edit":
            if not existing_code:
                return "Arquivo não encontrado para edição."
            prompt = (f"Edite este código {language}.\n"
                     f"Instrução: {description}\n\n"
                     f"Código original:\n{existing_code[:3000]}\n\n"
                     f"Responda APENAS com o código editado completo.")
            edited = _ask_ollama(prompt)
            if "```" in edited:
                lines = edited.split("\n")
                edited = "\n".join([l for l in lines if not l.startswith("```")])
            Path(file_path).write_text(edited, encoding="utf-8")
            return f"Código editado e salvo em {file_path}"

        elif action == "run":
            target = file_path or output_path
            if not target:
                return "Informe o arquivo para executar."
            
            ext = Path(target).suffix.lower()
            if ext == ".py":
                cmd = [sys.executable, target]
            elif ext == ".js":
                cmd = ["node", target]
            elif ext == ".sh":
                cmd = ["bash", target]
            else:
                cmd = [target]
            
            if args:
                cmd.extend(args.split())
            
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            output = result.stdout or result.stderr or "Sem output"
            if player:
                player.write_log(f"Run output: {output[:200]}")
            if speak and output:
                speak(f"Resultado da execução: {output[:300]}")
            return output[:1000]

        elif action == "review":
            target_code = existing_code or code
            prompt = (f"Faça uma revisão deste código {language} em português. "
                     f"Aponte problemas, melhorias e bugs:\n\n{target_code[:3000]}")
            review = _ask_ollama(prompt)
            if speak:
                speak(review[:500])
            return review

        else:
            return f"Ação desconhecida: {action}. Use write, edit, explain, run ou review."

    except subprocess.TimeoutExpired:
        return f"Execução excedeu timeout de {timeout}s"
    except Exception as e:
        return f"Erro code_helper/{action}: {e}"

def _get_ext(language: str) -> str:
    exts = {
        "python": "py", "javascript": "js", "typescript": "ts",
        "java": "java", "cpp": "cpp", "c": "c", "go": "go",
        "rust": "rs", "html": "html", "css": "css", "bash": "sh"
    }
    return exts.get(language.lower(), "txt")
