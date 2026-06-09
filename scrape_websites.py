"""
scrape_websites.py

Reads URLs from websites.txt, downloads each page, extracts the main readable
text, and writes one .txt file per website into data/raw/.

The output folder is the default input for chunk_documents.py.

Requires: requests, beautifulsoup4
"""

import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# --- Config (paths anchored to this script's location) ---
BASE_DIR = Path(__file__).resolve().parent
URL_FILE = BASE_DIR / "websites.txt"
OUTPUT_DIR = BASE_DIR / "data/raw"

REQUEST_TIMEOUT = 20  # seconds
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RAGIngestBot/1.0)"}


def read_urls(path: Path) -> list[str]:
    """Read URLs from file, one per line. Blank lines and # comments ignored."""
    if not path.exists():
        raise FileNotFoundError(f"URL file not found: {path}")
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


def clean_text(text: str) -> str:
    """Light cleaning: trim lines, drop empties, collapse runs of blanks."""
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    text = "\n".join(lines)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def slugify(value: str) -> str:
    """Turn a URL into a filesystem-safe filename stem."""
    parsed = urlparse(value)
    raw = (parsed.netloc + parsed.path).strip("/") if parsed.netloc else value
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", raw).strip("_")
    return slug or "page"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    urls = read_urls(URL_FILE)
    print(f"Loaded {len(urls)} URL(s) from {URL_FILE.name}")

    seen_slugs: dict[str, int] = {}
    written = 0

    for url in urls:
        print(f"Processing {url}")
        html = download(url)
        if html is None:
            continue

        try:
            cleaned = clean_text(extract_text(html))
        except Exception as e:
            print(f"  [extract error] {url}: {e}")
            continue

        if not cleaned:
            print(f"  [skip] no text extracted from {url}")
            continue

        # Unique filename even if two URLs slugify the same
        slug = slugify(url)
        if slug in seen_slugs:
            seen_slugs[slug] += 1
            slug = f"{slug}_{seen_slugs[slug]}"
        else:
            seen_slugs[slug] = 0

        try:
            (OUTPUT_DIR / f"{slug}.txt").write_text(cleaned, encoding="utf-8")
            written += 1
            print(f"  -> wrote {slug}.txt")
        except OSError as e:
            print(f"  [write error] {slug}.txt: {e}")

    print(f"\nDone. {written} file(s) written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
