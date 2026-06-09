"""
RAG ingestion pipeline: web pages + manual text + PDFs -> raw text -> chunks.

Sources:
  - URLs listed in websites.txt (downloaded with requests)
  - .txt / .md files dropped in manual/ (paste text there)
  - .pdf files dropped in pdfs/ (text extracted with pypdf)

Pipeline stages (same for all sources):
  1. Gather text (download a page, read a manual file, or extract a PDF)
  2. Extract main readable text (web: HTML parse; pdf: page text; manual: as-is)
  3. Save raw text to data/raw/<slug>.txt
  4. Light cleaning
  5. Chunk: ~450 words, 75-word overlap
  6. Append to data/processed/chunks.json

Requires: requests, beautifulsoup4, pypdf
"""

import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

# --- Config (paths anchored to this script's location) ---
BASE_DIR = Path(__file__).resolve().parent
URL_FILE = BASE_DIR / "websites.txt"
MANUAL_DIR = BASE_DIR / "manual"          # drop .txt / .md files here
PDF_DIR = BASE_DIR / "pdfs"               # drop .pdf files here
RAW_DIR = BASE_DIR / "data/raw"
PROCESSED_DIR = BASE_DIR / "data/processed"
CHUNKS_FILE = PROCESSED_DIR / "chunks.json"

MANUAL_EXTENSIONS = {".txt", ".md"}

CHUNK_SIZE = 450      # words per chunk
CHUNK_OVERLAP = 75    # words shared between consecutive chunks
REQUEST_TIMEOUT = 20  # seconds
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RAGIngestBot/1.0)"}


def read_urls(path: Path) -> list[str]:
    """Read URLs from file, one per line. Blank lines and # comments ignored."""
    if not path.exists():
        print(f"  [note] no URL file at {path}, skipping web sources")
        return []
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def download(url: str) -> str | None:
    """Download a webpage. Returns HTML text, or None on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"  [download error] {url}: {e}")
        return None


def extract_text(html: str) -> str:
    """Extract main readable text from HTML, dropping non-content tags."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer",
                     "aside", "noscript", "form"]):
        tag.decompose()
    return soup.get_text(separator="\n")


def extract_pdf_text(path: Path) -> str | None:
    """Extract text from a PDF, concatenating pages. None on failure."""
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            # Try empty-password decrypt; many PDFs are "encrypted" with no password
            try:
                reader.decrypt("")
            except Exception:
                print(f"  [pdf error] {path.name}: encrypted, cannot read")
                return None
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    except Exception as e:
        print(f"  [pdf error] {path.name}: {e}")
        return None


def clean_text(text: str) -> str:
    """Light cleaning: trim lines, drop empties, collapse runs of blanks."""
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    text = "\n".join(lines)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def slugify(value: str) -> str:
    """Turn a URL or name into a filesystem-safe filename stem."""
    parsed = urlparse(value)
    raw = (parsed.netloc + parsed.path).strip("/") if parsed.netloc else value
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", raw).strip("_")
    return slug or "source"


def chunk_words(text: str, size: int, overlap: int) -> list[str]:
    """Split text into word chunks of `size` with `overlap` shared words."""
    words = text.split()
    if not words:
        return []
    step = size - overlap
    chunks = []
    for start in range(0, len(words), step):
        chunk = words[start:start + size]
        if chunk:
            chunks.append(" ".join(chunk))
        if start + size >= len(words):
            break
    return chunks


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    all_chunks = []
    seen_slugs: dict[str, int] = {}

    def unique_slug(base: str) -> str:
        """Return a slug unique across this run (all source types combined)."""
        if base in seen_slugs:
            seen_slugs[base] += 1
            return f"{base}_{seen_slugs[base]}"
        seen_slugs[base] = 0
        return base

    def ingest_text(text: str, base_slug: str, source_label: str) -> None:
        """Clean, save raw, chunk, and append. Shared by all sources."""
        cleaned = clean_text(text)
        if not cleaned:
            print(f"  [skip] no text from {source_label}")
            return

        slug = unique_slug(base_slug)
        try:
            (RAW_DIR / f"{slug}.txt").write_text(cleaned, encoding="utf-8")
        except OSError as e:
            print(f"  [write error] {slug}.txt: {e}")
            return

        chunks = chunk_words(cleaned, CHUNK_SIZE, CHUNK_OVERLAP)
        for i, chunk in enumerate(chunks):
            all_chunks.append({
                "source": source_label,
                "chunk_id": f"{slug}_{i}",
                "text": chunk,
            })
        print(f"  -> {len(chunks)} chunk(s)")

    # --- Web sources ---
    urls = read_urls(URL_FILE)
    print(f"Loaded {len(urls)} URL(s) from {URL_FILE.name}")
    for url in urls:
        print(f"Processing {url}")
        html = download(url)
        if html is None:
            continue
        try:
            raw = extract_text(html)
        except Exception as e:
            print(f"  [extract error] {url}: {e}")
            continue
        ingest_text(raw, slugify(url), url)

    # --- Manual sources (pasted text files) ---
    manual_files = sorted(
        f for f in MANUAL_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in MANUAL_EXTENSIONS
    )
    print(f"\nFound {len(manual_files)} manual file(s) in {MANUAL_DIR.name}/")
    for f in manual_files:
        print(f"Processing {f.name}")
        try:
            content = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"  [read error] {f.name}: {e}")
            continue
        ingest_text(content, slugify(f.stem), f"manual:{f.name}")

    # --- PDF sources ---
    pdf_files = sorted(
        f for f in PDF_DIR.iterdir()
        if f.is_file() and f.suffix.lower() == ".pdf"
    )
    print(f"\nFound {len(pdf_files)} PDF file(s) in {PDF_DIR.name}/")
    if pdf_files and not PYPDF_AVAILABLE:
        print("  [skip] pypdf not installed; run: pip install pypdf")
    elif PYPDF_AVAILABLE:
        for f in pdf_files:
            print(f"Processing {f.name}")
            text = extract_pdf_text(f)
            if text is None:
                continue
            ingest_text(text, slugify(f.stem), f"pdf:{f.name}")

    # --- Write chunks ---
    try:
        CHUNKS_FILE.write_text(
            json.dumps(all_chunks, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        print(f"[write error] {CHUNKS_FILE}: {e}")
        return

    print(f"\nDone. {len(all_chunks)} total chunk(s) written to {CHUNKS_FILE}")


if __name__ == "__main__":
    main()