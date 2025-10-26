import os
from typing import Optional
from .abc import FileReader
import logging

logger = logging.getLogger(__name__)

# try optional dependencies
try:
    import PyPDF2
    _HAS_PYPDF2 = True
except Exception:
    _HAS_PYPDF2 = False

try:
    import docx as python_docx
    _HAS_PYDOCX = True
except Exception:
    _HAS_PYDOCX = False

try:
    import textract  # optional for .doc legacy formats
    _HAS_TEXTRACT = True
except Exception:
    _HAS_TEXTRACT = False

class TxtReader(FileReader):
    def read_text(self, file_path: str) -> str:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()

class PdfReader(FileReader):
    def read_text(self, file_path: str) -> str:
        if not _HAS_PYPDF2:
            raise RuntimeError("PyPDF2 not installed; install with: pip install PyPDF2")
        text_parts = []
        with open(file_path, "rb") as fh:
            reader = PyPDF2.PdfReader(fh)
            for page in reader.pages:
                try:
                    page_text = page.extract_text() or ""
                except Exception:
                    page_text = ""
                text_parts.append(page_text)
        return "\n".join(text_parts)

class DocxReader(FileReader):
    def read_text(self, file_path: str) -> str:
        if not _HAS_PYDOCX:
            raise RuntimeError("python-docx not installed; install with: pip install python-docx")
        doc = python_docx.Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs]
        return "\n".join(paragraphs)

class DocReader(FileReader):
    def read_text(self, file_path: str) -> str:
        # legacy .doc support - try textract if present
        if not _HAS_TEXTRACT:
            raise RuntimeError(
                "Reading .doc files requires 'textract'. Install with: pip install textract "
                "or convert .doc to .docx/.pdf before upload."
            )
        text = textract.process(file_path)
        try:
            return text.decode("utf-8", errors="ignore")
        except Exception:
            return str(text)

def get_reader_for_extension(ext: str) -> Optional[FileReader]:
    """
    Return an instance of FileReader for the given extension (ext without leading dot).
    """
    e = (ext or "").lower()
    if e == "txt":
        return TxtReader()
    if e == "pdf":
        return PdfReader()
    if e == "docx":
        return DocxReader()
    if e == "doc":
        return DocReader()
    return None
