from __future__ import annotations

import base64
import io
import os
from typing import Any

from fastapi import UploadFile
from pydantic import BaseModel, Field


class DocumentResult(BaseModel):
    file_name: str
    file_type: str
    extracted_text: str = ""
    extracted_tables: list[Any] = Field(default_factory=list)
    extracted_images: list[str] = Field(default_factory=list)
    page_count: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentProcessor:
    async def process(self, file: UploadFile) -> DocumentResult:
        return await process_document(file)


async def process_document(file: UploadFile) -> DocumentResult:
    filename = file.filename or "document"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
    content = await file.read()
    if hasattr(file, "seek"):
        await file.seek(0)

    if ext == "pdf":
        return await process_pdf(filename, content)
    if ext in {"png", "jpg", "jpeg", "webp"}:
        return await process_image(filename, ext, content)
    if ext in {"xlsx", "xls"}:
        return await process_spreadsheet(filename, content)
    if ext in {"docx", "doc"}:
        return await process_word(filename, content)
    if ext in {"py", "js", "ts", "java", "cpp", "c", "cs", "go", "rs", "html", "css", "sql"}:
        return await process_code(filename, ext, content)
    return await process_generic_text(filename, ext, content)


async def process_pdf(filename: str, content: bytes) -> DocumentResult:
    text_parts: list[str] = []
    tables: list[Any] = []
    pages = 1
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = len(pdf.pages)
            for page in pdf.pages:
                text_parts.append(page.extract_text() or "")
                for table in page.extract_tables() or []:
                    tables.append(table)
    except Exception:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(content))
            pages = len(reader.pages)
            text_parts = [(p.extract_text() or "") for p in reader.pages]
        except Exception as exc:
            text_parts = [f"[PDF extraction unavailable: {exc}]"]
    return DocumentResult(
        file_name=filename,
        file_type="pdf",
        extracted_text="\n\n".join(text_parts).strip(),
        extracted_tables=tables,
        page_count=pages,
        metadata={"size": len(content), "ocr_needed": not any(t.strip() for t in text_parts)},
    )


async def process_image(filename: str, ext: str, content: bytes) -> DocumentResult:
    encoded = base64.b64encode(content).decode("ascii")
    text = ""
    try:
        from PIL import Image
        import pytesseract
        image = Image.open(io.BytesIO(content))
        text = pytesseract.image_to_string(image, lang="por+eng")
    except Exception:
        text = "[OCR unavailable; image forwarded for multimodal analysis]"
    return DocumentResult(
        file_name=filename,
        file_type="image",
        extracted_text=text,
        extracted_images=[encoded],
        metadata={"extension": ext, "size": len(content)},
    )


async def process_spreadsheet(filename: str, content: bytes) -> DocumentResult:
    tables: list[Any] = []
    text_parts: list[str] = []
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=False)
        for ws in wb.worksheets:
            rows = []
            for row in ws.iter_rows(values_only=False):
                values = [cell.value for cell in row]
                rows.append(values)
            tables.append({"sheet": ws.title, "rows": rows})
            text_parts.append(f"Sheet: {ws.title}\n" + "\n".join(str(r) for r in rows[:200]))
    except Exception as exc:
        text_parts.append(f"[Spreadsheet extraction unavailable: {exc}]")
    return DocumentResult(
        file_name=filename,
        file_type="xlsx",
        extracted_text="\n\n".join(text_parts),
        extracted_tables=tables,
        metadata={"size": len(content)},
    )


async def process_word(filename: str, content: bytes) -> DocumentResult:
    text_parts: list[str] = []
    tables: list[Any] = []
    try:
        import docx
        doc = docx.Document(io.BytesIO(content))
        text_parts = [p.text for p in doc.paragraphs if p.text]
        for table in doc.tables:
            tables.append([[cell.text for cell in row.cells] for row in table.rows])
    except Exception as exc:
        text_parts = [f"[Word extraction unavailable: {exc}]"]
    return DocumentResult(
        file_name=filename,
        file_type="docx",
        extracted_text="\n".join(text_parts),
        extracted_tables=tables,
        metadata={"size": len(content)},
    )


async def process_code(filename: str, ext: str, content: bytes) -> DocumentResult:
    text = content.decode("utf-8", errors="replace")
    return DocumentResult(
        file_name=filename,
        file_type="code",
        extracted_text=text,
        metadata={"extension": ext, "lines": text.count(os.linesep) + 1},
    )


async def process_generic_text(filename: str, ext: str, content: bytes) -> DocumentResult:
    text = content.decode("utf-8", errors="replace")
    return DocumentResult(
        file_name=filename,
        file_type="txt",
        extracted_text=text,
        metadata={"extension": ext, "size": len(content)},
    )
