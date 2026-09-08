# rag/ingest_pdf.py

from typing import List

from pypdf import PdfReader


def extract_pdf_pages(path: str) -> List[str]:
    """Return the extracted text of each page in the PDF at `path`, in order."""
    reader = PdfReader(path)
    return [page.extract_text() or "" for page in reader.pages]


def extract_pdf_text(path: str) -> str:
    """Return the full extracted text of the PDF at `path`, pages joined by blank lines."""
    return "\n\n".join(p for p in extract_pdf_pages(path) if p.strip())
