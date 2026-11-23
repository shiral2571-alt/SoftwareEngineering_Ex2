"""Turn an uploaded file into plain text: code, essays in Word, PDFs (SRS FR-7.17).

History essays and other written homework usually arrive as .docx or .pdf. Reading those bytes as plain
text gives garbage, so each format is extracted properly. Scans and handwriting are not supported (no OCR).
"""
import io
import re
import zipfile
from xml.etree import ElementTree

MAX_FILE_BYTES = 10 * 1024 * 1024
TEXT_EXTENSIONS = (".txt", ".md", ".py", ".java", ".js", ".ts", ".c", ".cpp", ".cs", ".html", ".css", ".csv",
                   ".json", ".sql", ".kt", ".go", ".rb", ".php", ".vtt", ".srt")
SUPPORTED = TEXT_EXTENSIONS + (".docx", ".pdf")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class UnsupportedFile(ValueError):
    pass


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if len(data) > MAX_FILE_BYTES:
        raise UnsupportedFile("The file is larger than 10 MB")
    if name.endswith(".docx"):
        return _docx(data)
    if name.endswith(".pdf"):
        return _pdf(data)
    if name.endswith(TEXT_EXTENSIONS):
        return data.decode("utf-8-sig", errors="replace")
    raise UnsupportedFile(f"Unsupported file type. Use one of: {', '.join(SUPPORTED)}")


def _docx(data: bytes) -> str:
    """A .docx is a zip; the text is in word/document.xml, one <w:p> per paragraph. No extra library needed."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            root = ElementTree.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
        raise UnsupportedFile("This Word file could not be read") from None
    paragraphs = ["".join(t.text or "" for t in p.iter(f"{W}t")) for p in root.iter(f"{W}p")]
    return "\n".join(p for p in paragraphs if p.strip())


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader
    try:
        text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    except Exception:
        raise UnsupportedFile("This PDF could not be read") from None
    if not re.search(r"\w{2,}", text):
        raise UnsupportedFile("No text found in the PDF — is it a scan? Scanned or handwritten work is not supported")
    return text
