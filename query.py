"""
query.py — Retrieval + grounded generation for the roommate-matching RAG system.

Pipeline stage: Generation (the final box in the diagram).
This module takes a user question, pulls the top-k chunks from the vector store
(via the existing Milestone 4 retrieval function), and asks the LLM to answer
USING ONLY those chunks. Source attribution is computed in Python from the
retrieved chunks themselves — the LLM is never trusted to remember to cite.
"""

import os
import unicodedata
from pathlib import Path

from groq import Groq
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# LLM connection (Groq, OpenAI-compatible client)
# ---------------------------------------------------------------------------
load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "llama-3.3-70b-versatile"

# The exact sentence the system must return when the context is insufficient.
# Kept as a single constant so the prompt, the refusal check, and any caller
# all agree on one canonical string.
REFUSAL_MESSAGE = "I don't have enough information on that."

# ---------------------------------------------------------------------------
# Retrieval setup (Milestone 4 module: embed_and_retrieve.py).
#
# Your retrieve() takes TWO args: retrieve(query, collection). The collection
# is the ChromaDB store of embedded chunks, produced by build_collection().
# So we build (or reuse) that collection ONCE here at import time, then hand it
# to retrieve() on every call.
#
# Each retrieved chunk looks like:
#     {"text": ..., "source": ..., "chunk_index": ..., "distance": ...}
# `source` is top-level, which extract_source() already handles.
# ---------------------------------------------------------------------------
from embed_and_retrieve import load_chunks, build_collection, retrieve

# Resolve the chunks file relative to THIS script, matching how
# embed_and_retrieve.py locates it, so it works from any working directory.
_CHUNKS_PATH = Path(__file__).resolve().parent / "data" / "processed" / "chunks.json"

# Build/reuse the vector store once. build_collection uses get_or_create +
# upsert, so this is safe to re-run. It re-embeds the chunks on each launch;
# once that feels slow you can swap this for reusing the persisted ./chroma_store
# directly via chromadb.PersistentClient(...).get_collection("roommate_chunks").
COLLECTION = build_collection(load_chunks(str(_CHUNKS_PATH)))


# ---------------------------------------------------------------------------
# Helpers: source extraction + context formatting
# ---------------------------------------------------------------------------
def extract_source(chunk) -> str:
    """Pull the source document name out of a retrieved chunk.

    Defensive about shape so attribution still works whether the retriever
    nests the name under `metadata` or puts it at the top level.
    """
    if isinstance(chunk, dict):
        metadata = chunk.get("metadata")
        if isinstance(metadata, dict) and metadata.get("source"):
            return metadata["source"]
        if chunk.get("source"):
            return chunk["source"]
    return "unknown"


def chunk_text(chunk) -> str:
    """Pull the text body out of a retrieved chunk."""
    if isinstance(chunk, dict):
        return chunk.get("text", "")
    return str(chunk)


def format_context(chunks):
    """Turn retrieved chunks into a numbered context block + an ordered,
    de-duplicated list of source names.

    Returns:
        context_str: the text fed to the model, each chunk labelled with its source
        sources:     the list returned to the caller (this is the GUARANTEE —
                     attribution is derived from retrieval, not from the LLM)
    """
    context_parts = []
    sources = []
    for i, chunk in enumerate(chunks, start=1):
        text = chunk_text(chunk)
        source = extract_source(chunk)
        # Labelling each chunk with its source inside the prompt helps the model
        # ground its wording ("According to ..."), but it is NOT how we attribute.
        context_parts.append(f"[{i}] (source: {source})\n{text}")
        if source not in sources:
            sources.append(source)
    return "\n\n".join(context_parts), sources


def build_messages(question: str, context_str: str):
    """Construct the chat messages enforcing strict grounding.

    The rules live in the system message; the retrieved context + question live
    in the user message. The model is told, in no uncertain terms, that it may
    only use the supplied context and must emit the exact refusal string
    otherwise.
    """
    system_prompt = (
        "You are a question-answering assistant for a roommate-matching application. "
        "Answer the user's question using ONLY the information in the provided context. "
        "Rules you must follow strictly:\n"
        "1. Use only facts stated in the context below. Do not use any prior or general "
        "knowledge, and do not guess, speculate, or fill gaps from outside the context.\n"
        f"2. If the context does not contain enough information to answer, reply with "
        f"EXACTLY this sentence and nothing else: {REFUSAL_MESSAGE}\n"
        "3. When you can answer, ground it in the context "
        "(e.g. 'According to student reviews, ...')."
    )

    user_prompt = (
        f"Context:\n{context_str}\n\n"
        f"Question: {question}\n\n"
        "Answer using only the context above."
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _normalize(text: str) -> str:
    """Lowercase, strip, and normalize curly/straight apostrophes so the refusal
    check is robust to small punctuation differences from the model."""
    text = unicodedata.normalize("NFKC", text).strip().lower()
    return text.replace("\u2019", "'").rstrip(".")


def is_refusal(answer: str) -> bool:
    """True when the model returned the 'not enough information' response."""
    return _normalize(answer) == _normalize(REFUSAL_MESSAGE)


# ---------------------------------------------------------------------------
# End-to-end entry point
# ---------------------------------------------------------------------------
def ask(question: str) -> dict:
    """Answer a question strictly from retrieved context.

    Returns:
        {"answer": "<grounded answer or refusal>",
         "sources": ["source_a.txt", "source_b.txt"]}

    Source attribution is guaranteed programmatically: `sources` is built from
    the retrieved chunks in `format_context`, never parsed out of the LLM's
    reply. When the system refuses (no usable context), `sources` is empty so we
    never attribute a non-answer to documents.
    """
    chunks = retrieve(question, COLLECTION)

    # Hard grounding floor: with nothing retrieved there is nothing to ground on,
    # so we refuse without even calling the LLM.
    if not chunks:
        return {"answer": REFUSAL_MESSAGE, "sources": []}

    context_str, sources = format_context(chunks)
    messages = build_messages(question, context_str)

    # temperature=0 keeps grounding deterministic and discourages creative
    # (i.e. ungrounded) phrasing.
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0,
    )
    answer = response.choices[0].message.content.strip()

    # If the model declined, the retrieved chunks weren't actually used as the
    # basis of an answer, so we don't cite them.
    if is_refusal(answer):
        return {"answer": REFUSAL_MESSAGE, "sources": []}

    return {"answer": answer, "sources": sources}


# ---------------------------------------------------------------------------
# Test queries
# Queries 1-5 are the evaluation questions from planning.md (all expected to be
# answerable from the documents). Query 6 is deliberately OUT OF SCOPE: nothing
# in the roommate-matching corpus covers it, so the expected behavior is the
# exact refusal string.
# ---------------------------------------------------------------------------
TEST_QUERIES = [
    # 1 -> RoboPack (agricultural robotics club)
    "I'm interested in agricultural robotics. What club could help me meet people with that interest?",
    # 2 -> schedules don't overlap, so few chances to interact
    "Why would it be harder for a night owl and an early riser to become friends?",
    # 3 -> yes, multiple engineering students have roommate listings
    "Are there any engineering students currently looking for roommates?",
    # 4 -> yes; personality homophily research
    "Do roommates with similar personalities bond better than those with different ones?",
    # 5 -> not necessarily; deeper similarities + ongoing effort matter more than a spark
    "My potential roommate and I clicked right away, does that mean we'll actually get along long-term?",
    # 6 -> OUT OF SCOPE -> expected: "I don't have enough information on that."
    "What's the average cost of car insurance for a college student?",
]


if __name__ == "__main__":
    for q in TEST_QUERIES:
        result = ask(q)
        print(f"Q: {q}")
        print(f"A: {result['answer']}")
        print(f"Sources: {result['sources']}")
        print("-" * 70)