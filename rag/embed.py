"""Local semantic search ("embeddings"). Optional: without it the assistant uses keyword search only.

    pip install -r requirements-embeddings.txt
    python -m rag.embed download     # one-time: fetch the model (about 220 MB) and check it
    python -m rag.ingest             # rebuilds the keyword index and the vector index
    python -m rag.embed check        # is everything in place? does it find things?

Everything runs on this computer. Customer questions and knowledge-base text are never sent
anywhere for searching. The only network use is the one-time `download`.

Security rules (each has a test):
  * The model is a plain ONNX file plus a tokenizer: data, not Python code (no pickle files).
  * Downloads are pinned to one exact Hugging Face revision, and every file is checked against a
    SHA-256 hash written into this file. A file that does not match is never loaded.
  * The server never contacts the internet to load the model (offline mode is forced).
  * Vectors are stored as a plain float32 array (numpy `allow_pickle=False`) together with a
    description of what they belong to. If the knowledge base, model or file shape no longer
    matches, the vectors are ignored and keyword search is used instead.
  * Search results from vectors obey the same draft rule as keyword search: chunks marked
    (PROPOSED) stay hidden from customers.
"""
import hashlib
import json
import os
import re
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REPO = "Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
REVISION = "faf4aa4225822f3bc6376869cb1164e8e3feedd0"
PINNED = {  # SHA-256 of every file we load. Change only together with REVISION.
    "model_optimized.onnx": "634d0f66c29dc934c8fa72b8a4fe91dd4d420a22f1d82a241058d4316e659a99",
    "tokenizer.json": "fa685fc160bbdbab64058d4fc91b60e62d207e8dc60b9af5c002c5ab946ded00",
    "config.json": "c8ec081fdad2df991bf5abbf18418fec7a5cdaa421f60ffb060a30040b8c376f",
    "special_tokens_map.json": "8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835",
    "tokenizer_config.json": "0666eebf692422757e1dddf3c9fb1ded73ba3dc726c5828671fc89e45bf3609f",
}
MODEL_DIR = ROOT / "models" / "paraphrase-multilingual-MiniLM-L12-v2"
VEC_PATH = ROOT / "index" / "embeddings.npy"
META_PATH = ROOT / "index" / "embeddings.json"
WINDOW = 450          # characters per embedded window (the model reads about 128 tokens)
MAX_QUERY_CHARS = 500
MIN_SIM = float(os.environ.get("EMBED_MIN_SIM", "0.35"))


class ModelError(RuntimeError):
    pass


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify_model(model_dir=None, pinned=None):
    """Raise ModelError unless every pinned file exists and matches its hash."""
    model_dir, pinned = Path(model_dir or MODEL_DIR), pinned or PINNED
    for name, want in pinned.items():
        p = model_dir / name
        if not p.is_file():
            raise ModelError(f"model file missing: {name} (run: python -m rag.embed download)")
        if not want:
            raise ModelError(f"no pinned hash for {name}")
        if sha256_file(p) != want:
            raise ModelError(f"model file {name} does not match its pinned hash: not loading it")


def download():
    """Fetch the pinned model revision, then verify it."""
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=MODEL_REPO, revision=REVISION, allow_patterns=list(PINNED), local_dir=str(MODEL_DIR))
    verify_model()


# ---------- text windows ----------

def windows(chunk, limit=WINDOW):
    """Cut a chunk into pieces the model can read, each led by the section title."""
    title = chunk["heading"].split(" > ")[-1]
    pieces, cur = [], ""
    for para in re.split(r"(?<=[.!?])\s+|\n+", chunk["text"]):
        para = para.strip()
        if not para:
            continue
        if cur and len(cur) + len(para) + 1 > limit:
            pieces.append(cur)
            cur = para
        else:
            cur = f"{cur} {para}" if cur else para
    if cur:
        pieces.append(cur)
    return [f"{title}. {p}"[:limit + 120] for p in pieces] or [title]


def chunks_fingerprint(chunks):
    blob = json.dumps([[c["id"], c["heading"], c["text"]] for c in chunks], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------- the model ----------

class Embedder:
    def __init__(self):
        verify_model()
        os.environ.setdefault("HF_HUB_OFFLINE", "1")          # never reach the internet from here
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        from fastembed import TextEmbedding
        self.model = TextEmbedding(model_name=MODEL_NAME, specific_model_path=str(MODEL_DIR), threads=2)
        self.lock = threading.Lock()

    def embed(self, texts, batch_size=32):
        import numpy as np
        with self.lock:
            vecs = np.asarray(list(self.model.embed(list(texts), batch_size=batch_size)), dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / np.maximum(norms, 1e-9)


def build(chunks, embedder=None):
    """Embed every chunk window and save the vectors next to the keyword index."""
    import numpy as np
    embedder = embedder or Embedder()
    texts, owners = [], []
    for i, c in enumerate(chunks):
        for w in windows(c):
            texts.append(w)
            owners.append(i)
    vecs = embedder.embed(texts)
    VEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.save(VEC_PATH, vecs, allow_pickle=False)
    META_PATH.write_text(json.dumps({
        "model": MODEL_NAME, "revision": REVISION, "dim": int(vecs.shape[1]), "windows": len(texts),
        "chunks": len(chunks), "fingerprint": chunks_fingerprint(chunks), "owners": owners,
    }), encoding="utf-8")
    return len(texts)


class Vectors:
    """Saved vectors plus the model that turns a question into a vector."""

    def __init__(self, matrix, owners, n_chunks, embedder):
        self.matrix, self.owners, self.n_chunks, self.embedder = matrix, owners, n_chunks, embedder
        self._failed = False
        self._last = (None, None)  # the last question and its result: one chat turn asks about the same text twice

    def scores(self, query):
        """Best similarity per chunk (a list as long as the chunk list), or None if it cannot be computed.
        Callers must not change the returned array."""
        import numpy as np
        if self._failed:
            return None
        last_query, last_result = self._last
        if last_query == query:
            return last_result
        try:
            q = self.embedder.embed([query[:MAX_QUERY_CHARS]])[0]
            sims = self.matrix @ q
            best = np.full(self.n_chunks, -1.0, dtype=np.float32)
            np.maximum.at(best, self.owners, sims)
            self._last = (query, best)
            return best
        except Exception as e:  # never let search break the chat
            self._failed = True
            print(f"[embed] semantic search turned off: {type(e).__name__}: {e}", file=sys.stderr)
            return None


def check_files(chunks, vec_path=None, meta_path=None):
    """Return (matrix, owners) if the saved vectors belong to these chunks and this model, else raise ModelError."""
    import numpy as np
    vec_path, meta_path = Path(vec_path or VEC_PATH), Path(meta_path or META_PATH)
    if not (vec_path.is_file() and meta_path.is_file()):
        raise ModelError("no vector index yet (run: python -m rag.ingest)")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if (meta.get("model"), meta.get("revision")) != (MODEL_NAME, REVISION):
        raise ModelError("vector index was built with a different model")
    if meta.get("fingerprint") != chunks_fingerprint(chunks) or meta.get("chunks") != len(chunks):
        raise ModelError("vector index is out of date: knowledge base changed (run: python -m rag.ingest)")
    try:
        matrix = np.load(vec_path, allow_pickle=False)  # a file that needs pickle (code) is refused here
    except (ValueError, OSError, EOFError) as e:
        raise ModelError(f"vector index file is damaged or unsafe ({type(e).__name__})")
    owners = np.asarray(meta.get("owners", []), dtype=np.int64)
    if matrix.ndim != 2 or matrix.dtype != np.float32 or matrix.shape != (meta.get("windows"), meta.get("dim")) \
            or len(owners) != matrix.shape[0] or (len(owners) and (owners.min() < 0 or owners.max() >= len(chunks))):
        raise ModelError("vector index file is damaged")
    return matrix, owners


def load_vectors(chunks, quiet=False):
    """Vectors for these chunks, or None (keyword search only). Prints one line saying why."""
    def say(msg):
        if not quiet:
            print(f"[embed] {msg}; using keyword search only", file=sys.stderr)

    if os.environ.get("EMBEDDINGS", "on").strip().lower() in ("off", "0", "false", "no"):
        return None
    try:
        import numpy  # noqa: F401
        import fastembed  # noqa: F401
    except ImportError:
        return None  # not installed: this is the normal, supported setup
    try:
        matrix, owners = check_files(chunks)
        return Vectors(matrix, owners, len(chunks), Embedder())
    except ModelError as e:
        say(str(e))
    except Exception as e:
        say(f"{type(e).__name__}: {e}")
    return None


def build_if_possible(chunks):
    """Called by `python -m rag.ingest`. Builds vectors only if the model is already downloaded and verified."""
    try:
        import numpy  # noqa: F401
        import fastembed  # noqa: F401
    except ImportError:
        print("  semantic search: not installed (optional). See requirements-embeddings.txt")
        return
    try:
        verify_model()
    except ModelError as e:
        print(f"  semantic search: {e}")
        return
    n = build(chunks)
    print(f"  semantic search: embedded {n} text windows -> {VEC_PATH}")


def _cli(argv):
    cmd = argv[0] if argv else "check"
    if cmd == "download":
        print(f"Downloading {MODEL_REPO} at revision {REVISION[:10]} (about 220 MB)...")
        download()
        print("Downloaded and verified against the pinned hashes. Next: python -m rag.ingest")
    elif cmd == "build":
        from .ingest import build_chunks
        print("Embedded", build(build_chunks()), "windows.")
    elif cmd == "check":
        from .retrieve import Index
        from .ingest import INDEX_PATH
        try:
            verify_model()
            print("Model files: OK (match the pinned hashes)")
        except ModelError as e:
            sys.exit(f"Model files: {e}")
        idx = Index.load()
        if idx.vectors is None:
            sys.exit("Vector index: not in use (run: python -m rag.ingest, then check again)")
        print(f"Vector index: OK ({idx.vectors.matrix.shape[0]} windows for {len(idx.chunks)} chunks)")
        for q in ("how do I get my money back", "wie lange dauert eine Webseite", "xqzv plorb wumble"):
            hits = idx.search(q, k=3)
            print(f"  {q!r} ->", [c["file"] for _, c in hits] or "nothing")
    else:
        sys.exit("Usage: python -m rag.embed [download|build|check]")


if __name__ == "__main__":
    _cli(sys.argv[1:])
