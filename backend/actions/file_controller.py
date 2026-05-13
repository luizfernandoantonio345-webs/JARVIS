"""Gerenciamento avancado de arquivos e pastas."""
from __future__ import annotations

import shutil
from pathlib import Path

SHORTCUTS = {
    "desktop": Path.home() / "Desktop",
    "downloads": Path.home() / "Downloads",
    "documents": Path.home() / "Documents",
    "home": Path.home(),
    "pictures": Path.home() / "Pictures",
    "music": Path.home() / "Music",
    "videos": Path.home() / "Videos",
}


def _resolve_path(path: str) -> Path:
    if path.lower() in SHORTCUTS:
        return SHORTCUTS[path.lower()]
    return Path(path)


def file_controller(parameters: dict, player=None) -> str:
    action = parameters.get("action", "")
    path = parameters.get("path", "")
    destination = parameters.get("destination", "")
    new_name = parameters.get("new_name", "")
    content = parameters.get("content", "")
    name = parameters.get("name", "")
    extension = parameters.get("extension", "")
    count = parameters.get("count", 10)

    try:
        p = _resolve_path(path) if path else Path.home()

        if action == "list":
            if not p.exists():
                return f"Caminho nao encontrado: {p}"
            items = sorted(p.iterdir(), key=lambda x: x.name)
            files = [i.name for i in items if i.is_file()]
            dirs = [i.name for i in items if i.is_dir()]
            result = f"Pasta: {p}\n"
            if dirs:
                result += f"Pastas ({len(dirs)}): {', '.join(dirs[:10])}\n"
            if files:
                result += f"Arquivos ({len(files)}): {', '.join(files[:15])}"
            return result

        if action == "create_file":
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content or "", encoding="utf-8")
            return f"Arquivo criado: {p}"

        if action == "create_folder":
            p.mkdir(parents=True, exist_ok=True)
            return f"Pasta criada: {p}"

        if action == "delete":
            if p.is_file():
                p.unlink()
                return f"Arquivo deletado: {p}"
            if p.is_dir():
                shutil.rmtree(p)
                return f"Pasta deletada: {p}"
            return f"Nao encontrado: {p}"

        if action == "move":
            if not destination:
                return "Informe o destino para mover."
            dest = _resolve_path(destination)
            shutil.move(str(p), str(dest))
            return f"Movido: {p} -> {dest}"

        if action == "copy":
            if not destination:
                return "Informe o destino para copiar."
            dest = _resolve_path(destination)
            if p.is_file():
                shutil.copy2(str(p), str(dest))
            else:
                shutil.copytree(str(p), str(dest), dirs_exist_ok=True)
            return f"Copiado: {p} -> {dest}"

        if action == "rename":
            if not new_name:
                return "Informe o novo nome."
            new_path = p.parent / new_name
            p.rename(new_path)
            return f"Renomeado: {p.name} -> {new_name}"

        if action == "read":
            if not p.exists() or not p.is_file():
                return f"Arquivo nao encontrado: {p}"
            return p.read_text(encoding="utf-8", errors="replace")[:3000]

        if action == "write":
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content or "", encoding="utf-8")
            return f"Conteudo escrito em {p}"

        if action == "find":
            search_path = p if p.exists() else Path.home()
            pattern = f"**/*{name}*" if name else f"**/*{extension}"
            matches = list(search_path.glob(pattern))[:20]
            if not matches:
                return f"Nenhum arquivo encontrado para '{name or extension}'"
            return f"Encontrados {len(matches)}: " + ", ".join(str(m) for m in matches[:10])

        if action == "largest":
            search_path = p if p.exists() else Path.home() / "Downloads"
            files = [(f, f.stat().st_size) for f in search_path.rglob("*") if f.is_file()]
            files.sort(key=lambda x: x[1], reverse=True)
            result = f"Top {count} maiores arquivos em {search_path}:\n"
            for f, size in files[:count]:
                mb = size / (1024 * 1024)
                result += f"  {f.name}: {mb:.1f} MB\n"
            return result

        if action == "disk_usage":
            total, used, free = shutil.disk_usage(str(p) if p.exists() else "/")
            gb = 1024**3
            return (
                f"Disco em {p}:\n"
                f"Total: {total/gb:.1f} GB\n"
                f"Usado: {used/gb:.1f} GB ({used/total*100:.0f}%)\n"
                f"Livre: {free/gb:.1f} GB"
            )

        if action == "info":
            if not p.exists():
                return f"Nao encontrado: {p}"
            stat = p.stat()
            size_mb = stat.st_size / (1024 * 1024)
            from datetime import datetime

            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M")
            return (
                f"Nome: {p.name}\n"
                f"Tipo: {'Pasta' if p.is_dir() else 'Arquivo'}\n"
                f"Tamanho: {size_mb:.2f} MB\n"
                f"Modificado: {modified}\n"
                f"Caminho: {p}"
            )

        return f"Acao desconhecida: {action}"

    except PermissionError:
        return f"Sem permissao para acessar: {p}"
    except Exception as e:
        return f"Erro file_controller/{action}: {e}"
