from unittest.mock import MagicMock, patch

from rag.ingest_pdf import extract_pdf_pages, extract_pdf_text


def _fake_reader(page_texts):
    pages = []
    for text in page_texts:
        page = MagicMock()
        page.extract_text.return_value = text
        pages.append(page)
    reader = MagicMock()
    reader.pages = pages
    return reader


@patch("rag.ingest_pdf.PdfReader")
def test_extract_pdf_pages_returns_text_per_page(mock_reader_cls):
    mock_reader_cls.return_value = _fake_reader(["page one", "page two"])

    pages = extract_pdf_pages("fake.pdf")

    assert pages == ["page one", "page two"]


@patch("rag.ingest_pdf.PdfReader")
def test_extract_pdf_pages_handles_none_from_extract_text(mock_reader_cls):
    mock_reader_cls.return_value = _fake_reader([None, "page two"])

    pages = extract_pdf_pages("fake.pdf")

    assert pages == ["", "page two"]


@patch("rag.ingest_pdf.PdfReader")
def test_extract_pdf_text_joins_nonblank_pages(mock_reader_cls):
    mock_reader_cls.return_value = _fake_reader(["page one", "  ", "page two"])

    text = extract_pdf_text("fake.pdf")

    assert text == "page one\n\npage two"
