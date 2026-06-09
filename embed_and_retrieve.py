"""
Embedding + Retrieval stage for the roommate-matching RAG pipeline.

Pipeline context:
    Document Ingestion -> Chunking -> [ Embedding + Vector Store ] -> Retrieval -> Generation
                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                      This file covers the highlighted middle stages.

What this script does, in order:
    1. Loads the chunks produced by your ingestion / chunking pipeline.
    2. Embeds every chunk with the local model all-MiniLM-L6-v2.
    3. Stores the chunks + embeddings + metadata in ChromaDB.
    4. Exposes retrieve(query, k=5), which returns the top-k most relevant
       chunks for a query, each with its text and source metadata.

Install the two libraries first:
    pip install sentence-transformers chromadb
"""

import json
import sys
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer


# ---------------------------------------------------------------------------
# 1. Load the embedding model ONCE.
# ---------------------------------------------------------------------------
# Loading a model is slow (it reads weights from disk), so we do it a single
# time at the top of the file instead of inside a function that gets called
# repeatedly. all-MiniLM-L6-v2 turns any piece of text into a 384-number
# vector ("embedding"). Texts with similar meaning get similar vectors.
model = SentenceTransformer("all-MiniLM-L6-v2")


# ---------------------------------------------------------------------------
# 2. Load the chunks coming out of your ingestion pipeline.
# ---------------------------------------------------------------------------
# ASSUMPTION about the input format -- adjust this one function if yours
# differs. This expects a JSON file holding a list of chunk objects:
#
#   [
#     {"text": "Alpha is a junior...", "source": "roomsurf.txt", "chunk_index": 0},
#     {"text": "Beta prefers quiet...", "source": "roomsurf.txt", "chunk_index": 1},
#     ...
#   ]
#
# Each chunk needs three things:
#   - text:        the chunk's actual content (what gets embedded)
#   - source:      the source document name  (metadata you asked for)
#   - chunk_index: position of the chunk within that document (metadata)
def load_chunks(path: str):
    """Read the chunk list from a JSON file and return it as a Python list."""
    with open(path, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    print(f"Loaded {len(chunks)} chunks from {path}")
    return chunks


# ---------------------------------------------------------------------------
# 3 + 4. Embed the chunks and store everything in ChromaDB.
# ---------------------------------------------------------------------------
def build_collection(chunks, persist_path: str = "./chroma_store"):
    """
    Embed every chunk and store it (with metadata) in a ChromaDB collection.
    Returns the collection so the retrieve() function can query it.
    """

    # PersistentClient writes the database to disk at `persist_path`, so your
    # embeddings survive after the script ends. (chromadb.Client() instead
    # would keep everything in memory only and vanish when the program exits.)
    client = chromadb.PersistentClient(path=persist_path)

    # A "collection" is ChromaDB's table-like container for a set of vectors.
    # get_or_create_collection: reuse it if it already exists, otherwise make
    # a new one -- so re-running the script doesn't crash.
    #
    # metadata={"hnsw:space": "cosine"} tells Chroma to rank results by COSINE
    # similarity. The default is "l2" (squared Euclidean distance). For
    # sentence-transformer embeddings, cosine is the conventional choice
    # because it compares the *direction* of vectors (meaning) rather than
    # their raw magnitude. You can delete this line to use the default.
    collection = client.get_or_create_collection(
        name="roommate_chunks",
        metadata={"hnsw:space": "cosine"},
    )

    # --- Turn the chunks into the four parallel lists Chroma's API expects ---

    # texts: the strings we feed to the embedding model.
    texts = [c["text"] for c in chunks]

    # embeddings: encode() returns a NumPy array; .tolist() converts it to
    # plain Python lists, which is what Chroma wants. One 384-number vector
    # per chunk.
    embeddings = model.encode(texts).tolist()

    # ids + metadata. Every item in a Chroma collection needs a UNIQUE string
    # id, and we also store the source name + position as metadata.
    #
    # Your chunks.json has "text" and "source" but no explicit position field,
    # so we DERIVE the index here: for each chunk we count how many chunks
    # we've already seen from the same source, and use that running count as
    # the position. (This assumes chunks.json is in document order, which your
    # ingestion step should produce. If a chunk DOES carry its own index, we
    # use that instead.)
    ids = []
    metadatas = []
    seen_per_source = {}  # source name -> how many of its chunks we've seen
    for c in chunks:
        source = c["source"]

        # Prefer an explicit position if the chunk has one; otherwise derive it.
        if "chunk_index" in c:
            index = c["chunk_index"]
        else:
            index = seen_per_source.get(source, 0)
        seen_per_source[source] = seen_per_source.get(source, 0) + 1

        ids.append(f"{source}::chunk_{index}")
        # metadata values must be simple types (str, int, float, bool).
        metadatas.append({"source": source, "chunk_index": index})

    # upsert() inserts new items and overwrites any with an id that already
    # exists. We use it instead of add() so re-running the script updates the
    # store cleanly rather than throwing a "duplicate id" error. (add() does
    # the same insert but errors on ids that already exist.)
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=texts,      # Chroma keeps the original text next to the vector
        metadatas=metadatas,
    )

    print(f"Stored {collection.count()} chunks in collection 'roommate_chunks'")
    return collection


# ---------------------------------------------------------------------------
# 5. The retrieval function.
# ---------------------------------------------------------------------------
def retrieve(query: str, collection, k: int = 5):
    """
    Embed `query`, search ChromaDB, and return the top-k matching chunks.

    Each returned item is a dict with:
        text        -> the chunk's content
        source      -> which document it came from
        chunk_index -> its position within that document
        distance    -> similarity score (lower = more similar with cosine)
    """

    # Embed the query the SAME way we embedded the chunks. We wrap `query` in a
    # list because encode() works on a batch; the result is a list of one
    # vector, which matches what query_embeddings expects below.
    query_embedding = model.encode([query]).tolist()

    # query() finds the n_results vectors closest to our query vector.
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=k,
    )

    # IMPORTANT shape detail: because Chroma supports searching many queries at
    # once, each field below is a LIST OF LISTS. We sent one query, so our
    # results live at index [0].
    documents = results["documents"][0]    # list of k chunk texts
    metadatas = results["metadatas"][0]    # list of k metadata dicts
    distances = results["distances"][0]    # list of k distance scores

    # Zip the three parallel lists back together into clean per-chunk dicts.
    matches = []
    for text, meta, dist in zip(documents, metadatas, distances):
        matches.append(
            {
                "text": text,
                "source": meta["source"],
                "chunk_index": meta["chunk_index"],
                "distance": dist,
            }
        )
    return matches


# ---------------------------------------------------------------------------
# Demo: build the store, then run one of your evaluation-plan questions.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Path to your ingestion pipeline's output. By default we look relative to
    # THIS script's location (not wherever you happen to run Python from), so
    # it resolves correctly no matter your current working directory. Your
    # layout is: <project root>/embed_and_retrieve.py and
    #            <project root>/data/processed/chunks.json
    # Override it by passing a path as the first command-line argument, e.g.:
    #     python embed_and_retrieve.py some/other/chunks.json
    script_dir = Path(__file__).resolve().parent
    default_path = script_dir / "data" / "processed" / "chunks.json"
    chunks_path = sys.argv[1] if len(sys.argv) > 1 else str(default_path)
    chunks = load_chunks(chunks_path)

    # Embed + store everything (do this once; afterwards you can comment it out
    # and just reuse the persisted ./chroma_store).
    collection = build_collection(chunks)

    # The five evaluation questions from your planning.md. We run each one
    # through retrieve() and print the top-k chunks so you can eyeball whether
    # the retrieved text actually supports your expected answer.
    eval_questions = [
        "I'm interested in agricultural robotics. What club could help me meet people with that interest?",
        "Why would it be harder for a night owl and an early riser to become friends?",
        "Are there any engineering students currently looking for roommates?",
        "Do roommates with similar personalities bond better than those with different ones?",
        "My potential roommate and I clicked right away, does that mean we'll actually get along long-term?",
    ]

    for q_num, query in enumerate(eval_questions, start=1):
        top_chunks = retrieve(query, collection, k=5)

        print("\n" + "=" * 70)
        print(f"Question {q_num}: {query}")
        print("=" * 70)
        for rank, chunk in enumerate(top_chunks, start=1):
            print(f"\n--- Result {rank} (distance {chunk['distance']:.4f}) ---")
            print(f"Source: {chunk['source']}  (chunk #{chunk['chunk_index']})")
            print(chunk["text"])