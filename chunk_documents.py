"""
chunk_documents.py

Reads documents from the manual/ and pdfs/ folders, lightly cleans each, splits
into recursive sentence-aware chunks (~450 words, 75-word overlap), and writes
data/processed/chunks.json.

  - manual/ : pasted .txt / .md files
  - pdfs/   : .pdf files (text extracted with pypdf)

Usage:
    python chunk_documents.py

Requires: pypdf  (only needed if pdfs/ contains PDFs)
"""

import json
import re
from pathlib import Path

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

# --- Config (paths anchored to this script's location) ---
BASE_DIR = Path(__file__).resolve().parent
MANUAL_DIR = BASE_DIR / "manual"   # pasted .txt / .md files
PDF_DIR = BASE_DIR / "pdfs"        # .pdf files
PROCESSED_DIR = BASE_DIR / "data/processed"
CHUNKS_FILE = PROCESSED_DIR / "chunks.json"

TEXT_EXTENSIONS = {".txt", ".md"}

CHUNK_SIZE = 450      # words per chunk
CHUNK_OVERLAP = 75    # words shared between consecutive chunks


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


# Abbreviations whose trailing "." must NOT be treated as a sentence end.
# Important for academic sources (citations like "et al., Vol. 7, No. 7").
_ABBREVIATIONS = [
    "et al.", "Vol.", "No.", "Nos.", "pp.", "p.", "Dr.", "Mr.", "Mrs.", "Ms.",
    "Prof.", "Ph.D.", "PhD.", "M.D.", "B.A.", "M.A.", "e.g.", "i.e.", "etc.",
    "Inc.", "Ltd.", "Co.", "U.S.", "U.K.", "vs.", "Fig.", "Figs.", "cf.",
    "Eds.", "Ed.", "Jr.", "Sr.", "St.", "approx.", "Vol", "No",
]
_PLACEHOLDER = "\x00"
# Split after . ! ? (plus optional closing quote/bracket) when followed by
# whitespace and something that looks like the start of a new sentence.
_SENTENCE_RE = re.compile(
    r'(?<=[.!?])["\u201d\u2019\')\]]*\s+(?=[A-Z0-9"\u201c\u2018\'(\[])'
)


def split_sentences(block: str) -> list[str]:
    """Split a line/paragraph into sentences, protecting known abbreviations."""
    protected = block
    for ab in _ABBREVIATIONS:
        protected = protected.replace(ab, ab.replace(".", _PLACEHOLDER))
    parts = _SENTENCE_RE.split(protected)
    return [p.replace(_PLACEHOLDER, ".").strip() for p in parts if p.strip()]


def split_into_units(text: str) -> list[str]:
    """Recursive hierarchy: split on lines/paragraphs first, then sentences."""
    units = []
    for block in text.split("\n"):
        block = block.strip()
        if block:
            units.extend(split_sentences(block))
    return units


def hard_split(unit: str, size: int) -> list[str]:
    """Fallback for a single 'sentence' longer than the chunk size."""
    words = unit.split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]


def is_heading(unit: str) -> bool:
    """A short line with no terminal punctuation — likely a heading/title."""
    s = unit.strip()
    return bool(s) and len(s.split()) <= 12 and not _ENDS_SENTENCE.search(s)


_ENDS_SENTENCE = re.compile(r'[.!?]["\u201d\u2019\')\]]?$')


def chunk_words(text: str, size: int, overlap: int) -> list[str]:
    """Recursively pack whole sentences into ~`size`-word chunks.

    Chunks begin and end on sentence boundaries (never mid-sentence), the
    `overlap` is filled with whole trailing sentences, and a trailing heading is
    carried to the next chunk so it leads its own section rather than dangling.
    A sentence longer than `size` is hard-split as a fallback.
    """
    units: list[str] = []
    for unit in split_into_units(text):
        if len(unit.split()) > size:
            units.extend(hard_split(unit, size))
        else:
            units.append(unit)

    chunks: list[str] = []
    current: list[str] = []
    cur_words = 0

    for unit in units:
        uw = len(unit.split())
        if current and cur_words + uw > size:
            # Don't end a chunk on heading lines — carry them to the next chunk.
            carried: list[str] = []
            while len(current) > 1 and is_heading(current[-1]):
                carried.insert(0, current.pop())
            chunks.append(" ".join(current))
            # Seed the next chunk with trailing whole sentences (~overlap words).
            seed: list[str] = []
            sw = 0
            for u in reversed(current):
                if sw >= overlap:
                    break
                seed.insert(0, u)
                sw += len(u.split())
            current = seed + carried
            cur_words = sum(len(u.split()) for u in current)
        current.append(unit)
        cur_words += uw

    if current:
        chunks.append(" ".join(current))
    return chunks


# --- Special-case chunking for Roomsurf profile dumps --------------------
# Roomsurf pages pack many student profiles into one file. The generic
# ~450-word chunker would blend several people into a single embedding (which
# is why an "engineering student" query couldn't find Beta/Gamma/Epsilon), so
# we split ONE profile per chunk instead. Each profile begins with the
# object-replacement glyph "\uFFFC" (shows as the box character) followed by
# the name, e.g. "<glyph> Beta Male - 2030 ...".
_ROOMSURF_BOILERPLATE = re.compile(
    r"🔓 Create an Account to see \S+['\u2019]s (?:bio|Social Media handles)"
)


def chunk_roomsurf(text: str) -> list[str]:
    """Split a Roomsurf dump into one clean chunk per student profile."""
    # Split on the per-profile marker glyph; drop the empty piece before the
    # first profile.
    profiles = [p.strip() for p in text.split("\uFFFC") if p.strip()]

    chunks: list[str] = []
    for profile in profiles:
        # Remove the repeated "Create an Account to see ..." prompts. They
        # appear on every profile, carry no matching signal, and only pull the
        # embedding toward a generic "Roomsurf page" centroid.
        cleaned = _ROOMSURF_BOILERPLATE.sub("", profile)
        # Collapse the whitespace the removals leave behind.
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            chunks.append(cleaned)
    return chunks


def load_file_text(path: Path) -> str | None:
    """Read a .txt/.md file directly, or extract text from a .pdf."""
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"  [read error] {path.name}: {e}")
            return None
    if suffix == ".pdf":
        if not PYPDF_AVAILABLE:
            print(f"  [skip] {path.name}: pypdf not installed (pip install pypdf)")
            return None
        return extract_pdf_text(path)
    return None  # unsupported extension


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    supported = TEXT_EXTENSIONS | {".pdf"}
    # Scan the manual/ and pdfs/ folders only.
    search_dirs = [d for d in (MANUAL_DIR, PDF_DIR) if d.is_dir()]
    if not search_dirs:
        raise NotADirectoryError(f"No input folders found (checked {MANUAL_DIR}, "
                                 f"{PDF_DIR})")

    # Gather files; dedupe by resolved path so a file in both folders isn't double-read.
    files, seen_paths = [], set()
    for d in search_dirs:
        found = [f for f in sorted(d.iterdir())
                 if f.is_file() and f.suffix.lower() in supported]
        print(f"Found {len(found)} file(s) in {d}")
        for f in found:
            if f.resolve() not in seen_paths:
                files.append(f)
                seen_paths.add(f.resolve())

    all_chunks = []
    seen_slugs: dict[str, int] = {}
    for f in files:
        print(f"Processing {f.name}")
        text = load_file_text(f)
        if text is None:
            continue

        cleaned = clean_text(text)
        if not cleaned:
            print(f"  [skip] no text in {f.name}")
            continue

        # Keep chunk_ids unique even if two folders hold files with the same stem.
        slug = f.stem
        if slug in seen_slugs:
            seen_slugs[slug] += 1
            slug = f"{slug}_{seen_slugs[slug]}"
        else:
            seen_slugs[slug] = 0

        # Roomsurf profile dumps get one-profile-per-chunk treatment; every
        # other source uses the generic ~450-word sentence-aware chunker.
        if "roomsurf" in f.name.lower():
            chunks = chunk_roomsurf(cleaned)
        else:
            chunks = chunk_words(cleaned, CHUNK_SIZE, CHUNK_OVERLAP)
        for i, chunk in enumerate(chunks):
            all_chunks.append({
                "source": f.name,
                "chunk_id": f"{slug}_{i}",
                "text": chunk,
            })
        print(f"  -> {len(chunks)} chunk(s)")

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