"""Controle da area de trabalho."""

import ctypes
import platform
import shutil
from pathlib import Path

DESKTOP = Path.home() / "Desktop"

EXTENSIONS = {
    "Imagens": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp"],
    "Videos": [".mp4", ".avi", ".mkv", ".mov", ".wmv"],
    "Documentos": [".pdf", ".doc", ".docx", ".txt", ".xlsx", ".pptx"],
    "Audio": [".mp3", ".wav", ".flac", ".m4a"],
    "Codigo": [".py", ".js", ".html", ".css", ".json", ".ts"],
    "Compactados": [".zip", ".rar", ".7z", ".tar"],
    "Outros": [],
}


def desktop_control(parameters: dict, player=None) -> str:
    action = parameters.get("action", "")

    try:
        if action == "wallpaper":
            path = parameters.get("path", "")
            if platform.system() == "Windows":
                ctypes.windll.user32.SystemParametersInfoW(20, 0, path, 3)
                return f"Wallpaper alterado para {path}"
            return "Suporte apenas Windows por enquanto"

        elif action == "wallpaper_url":
            import httpx

            url = parameters.get("url", "")
            save_path = str(Path.home() / "Downloads" / "wallpaper.jpg")
            with httpx.Client() as client:
                r = client.get(url)
                with open(save_path, "wb") as f:
                    f.write(r.content)
            if platform.system() == "Windows":
                ctypes.windll.user32.SystemParametersInfoW(20, 0, save_path, 3)
            return "Wallpaper baixado e aplicado"

        elif action == "organize":
            mode = parameters.get("mode", "by_type")
            moved = 0
            for item in DESKTOP.iterdir():
                if item.is_file() and item.suffix:
                    if mode == "by_type":
                        folder_name = "Outros"
                        for cat, exts in EXTENSIONS.items():
                            if item.suffix.lower() in exts:
                                folder_name = cat
                                break
                    else:
                        folder_name = item.stat().st_mtime.__class__.__name__

                    dest = DESKTOP / folder_name
                    dest.mkdir(exist_ok=True)
                    shutil.move(str(item), str(dest / item.name))
                    moved += 1
            return f"Desktop organizado: {moved} arquivos movidos"

        elif action == "list":
            items = list(DESKTOP.iterdir())
            names = [i.name for i in items[:20]]
            return f"Desktop ({len(items)} itens): {', '.join(names)}"

        elif action == "stats":
            files = [i for i in DESKTOP.iterdir() if i.is_file()]
            folders = [i for i in DESKTOP.iterdir() if i.is_dir()]
            return f"Desktop: {len(files)} arquivos, {len(folders)} pastas"

        elif action == "clean":
            removed = 0
            for item in DESKTOP.iterdir():
                if item.suffix in [".lnk", ".tmp", ".log"]:
                    item.unlink()
                    removed += 1
            return f"Desktop limpo: {removed} arquivos temporarios removidos"

        else:
            return f"Acao desconhecida: {action}"

    except Exception as e:
        return f"Erro desktop_control/{action}: {e}"
