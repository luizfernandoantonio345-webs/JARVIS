"""Processa qualquer tipo de arquivo."""

from pathlib import Path


def file_processor(parameters: dict, player=None, speak=None) -> str:
    file_path = parameters.get("file_path", "")
    action = parameters.get("action", "")
    instruction = parameters.get("instruction", "")
    _ = instruction  # reservado para uso futuro

    if not file_path or not Path(file_path).exists():
        return f"Arquivo nao encontrado: {file_path}"

    ext = Path(file_path).suffix.lower()

    try:
        # PDF
        if ext == ".pdf":
            import PyPDF2

            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                text = "\n".join(p.extract_text() or "" for p in reader.pages)
            if action in ["summarize", "resumir"]:
                return f"PDF com {len(reader.pages)} paginas. Primeiros 1000 chars:\n{text[:1000]}"
            return text[:3000]

        # Word
        elif ext in [".docx", ".doc"]:
            from docx import Document

            doc = Document(file_path)
            text = "\n".join(p.text for p in doc.paragraphs)
            if action == "summarize":
                return f"Documento Word:\n{text[:1000]}"
            return text[:3000]

        # Excel/CSV
        elif ext in [".xlsx", ".xls", ".csv"]:
            if ext == ".csv":
                import csv

                with open(file_path, "r", encoding="utf-8") as f:
                    rows = list(csv.reader(f))
                return (
                    f"CSV: {len(rows)} linhas, {len(rows[0]) if rows else 0} colunas\n"
                    "Primeiras linhas:\n"
                    + "\n".join([",".join(r) for r in rows[:5]])
                )
            else:
                import openpyxl

                wb = openpyxl.load_workbook(file_path)
                ws = wb.active
                data = list(ws.iter_rows(values_only=True))
                return f"Excel: {len(data)} linhas, {len(data[0]) if data else 0} colunas"

        # Imagem
        elif ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"]:
            from PIL import Image

            img = Image.open(file_path)
            if action in ["info", "describe"]:
                return f"Imagem: {img.size[0]}x{img.size[1]}px, modo {img.mode}, formato {img.format}"
            elif action == "resize":
                w = parameters.get("width", img.size[0] // 2)
                h = parameters.get("height", img.size[1] // 2)
                img = img.resize((w, h))
                out = file_path.replace(ext, f"_resized{ext}")
                img.save(out)
                return f"Imagem redimensionada: {out}"
            elif action == "convert":
                fmt = parameters.get("format", "png")
                out = file_path.replace(ext, f".{fmt}")
                img.save(out)
                return f"Convertido para {out}"
            return f"Imagem: {img.size}, {img.mode}"

        # Texto/Codigo
        elif ext in [".txt", ".py", ".js", ".html", ".css", ".json", ".md"]:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            if action == "summarize":
                return (
                    f"Arquivo de {len(content)} chars, {len(content.splitlines())} linhas:\n"
                    f"{content[:500]}"
                )
            return content[:3000]

        # Audio
        elif ext in [".mp3", ".wav", ".flac", ".m4a"]:
            if action == "transcribe":
                from faster_whisper import WhisperModel

                model = WhisperModel("tiny", device="cpu", compute_type="int8")
                segments, _ = model.transcribe(file_path, language="pt")
                return " ".join(s.text for s in segments)
            elif action == "info":
                import mutagen

                audio = mutagen.File(file_path)
                return f"Audio: {audio.info.length:.1f}s, {audio.info.sample_rate}Hz"
            return f"Arquivo de audio: {file_path}"

        else:
            return f"Tipo de arquivo nao suportado: {ext}"

    except ImportError as e:
        return f"Dependencia faltando: {e}. Instale com pip install <pacote>"
    except Exception as e:
        return f"Erro ao processar arquivo: {e}"
