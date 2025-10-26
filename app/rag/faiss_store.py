import os
import logging
import json
import numpy as np

logger = logging.getLogger(__name__)

try:
    import faiss
except Exception as e:
    raise RuntimeError(
        "faiss is required for the FAISS vector store. Install with: pip install faiss-cpu\n"
        f"Original import error: {e}"
    )

class FaissStore:
    """
    FAISS-backed local vector store with persistent index + metadata.

    - index file: app/static/vector_store/faiss.index
    - metadata file: app/static/vector_store/metadata.json

    API:
      upsert_vectors(vectors: list[{'id': str, 'values': [float], 'metadata': dict}])
      delete_vectors(ids: list[str])
      query(embedding, top_k=5, include_metadata=True) -> returns dict similar to pinecone response
    """

    def __init__(self, index_name: str = None, api_key: str = None, environment: str = None):
        # storage paths
        base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "vector_store")
        os.makedirs(base, exist_ok=True)
        self.index_path = os.path.join(base, "faiss.index")
        self.meta_path = os.path.join(base, "metadata.json")

        # internal structures
        self.dim = None
        self.index = None  # faiss index (IndexIDMap over a flat index)
        self.next_int_id = 1
        # mapping string_id -> int_id and metadata dict
        self.id_to_int = {}
        self.int_to_id = {}
        self.metadata = {}  # string_id -> metadata dict

        # load existing store if present
        if os.path.exists(self.meta_path) and os.path.exists(self.index_path):
            try:
                with open(self.meta_path, "r", encoding="utf-8") as fh:
                    meta = json.load(fh)
                    self.dim = meta.get("dim")
                    self.next_int_id = int(meta.get("next_int_id", 1))
                    self.id_to_int = meta.get("id_to_int", {})
                    # convert keys of id_to_int to str->int
                    self.id_to_int = {str(k): int(v) for k, v in self.id_to_int.items()}
                    self.int_to_id = {int(v): str(k) for k, v in self.id_to_int.items()}
                    self.metadata = meta.get("metadata", {})
                # load faiss index
                self.index = faiss.read_index(self.index_path)
                logger.info("Loaded FAISS index with dim=%s and %d vectors", self.dim, len(self.id_to_int))
            except Exception:
                logger.exception("Failed to load existing FAISS index or metadata; starting fresh")
                self.index = None
                self.dim = None
                self.id_to_int = {}
                self.int_to_id = {}
                self.metadata = {}
                self.next_int_id = 1

    def _save_meta_and_index(self):
        # save metadata
        meta = {
            "dim": self.dim,
            "next_int_id": self.next_int_id,
            "id_to_int": self.id_to_int,
            "metadata": self.metadata
        }
        with open(self.meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh)
        # save index
        if self.index is not None:
            faiss.write_index(self.index, self.index_path)

    def _ensure_index(self, dim: int):
        if self.index is None:
            self.dim = int(dim)
            # use inner product on normalized vectors for cosine similarity
            flat = faiss.IndexFlatIP(self.dim)
            self.index = faiss.IndexIDMap(flat)
            logger.info("Created new FAISS index with dim=%s", self.dim)

    def upsert_vectors(self, vectors: list):
        """
        vectors: list of dicts: { 'id': str, 'values': list[float], 'metadata': dict }
        """
        if not vectors:
            return
        # prepare numpy array
        vecs = []
        ids_int = []
        for v in vectors:
            sid = str(v["id"])
            vals = np.array(v["values"], dtype="float32")
            if self.dim is None:
                self._ensure_index(len(vals))
            if len(vals) != self.dim:
                raise ValueError(f"Embedding dimension mismatch: expected {self.dim}, got {len(vals)}")
            # normalize for cosine similarity (optional)
            norm = np.linalg.norm(vals)
            if norm > 0:
                vals = vals / norm
            # assign or reuse int id
            if sid in self.id_to_int:
                int_id = self.id_to_int[sid]
                # remove existing vector for update: faiss supports remove_ids
                try:
                    self.index.remove_ids(np.array([int(int_id)], dtype="int64"))
                except Exception:
                    # if removal fails, continue (we'll add again)
                    logger.debug("remove_ids failed for id %s", int_id)
            else:
                int_id = self.next_int_id
                self.next_int_id += 1
                self.id_to_int[sid] = int_id
                self.int_to_id[int_id] = sid
            vecs.append(vals.astype("float32"))
            ids_int.append(int(int_id))
            # update metadata
            if "metadata" in v and v["metadata"] is not None:
                self.metadata[sid] = v["metadata"]
        if vecs:
            arr = np.vstack(vecs)
            ids_np = np.array(ids_int, dtype="int64")
            try:
                self.index.add_with_ids(arr, ids_np)
            except Exception:
                # fallback: index.add then map ids via IndexIDMap (if not IDMap initially)
                try:
                    self.index.add_with_ids(arr, ids_np)
                except Exception:
                    logger.exception("Failed to add vectors to FAISS index")
                    raise
        # persist
        self._save_meta_and_index()

    def delete_vectors(self, ids: list):
        if not ids:
            return
        int_ids = []
        for sid in ids:
            sid = str(sid)
            if sid in self.id_to_int:
                int_id = self.id_to_int.pop(sid)
                int_ids.append(int(int_id))
                # remove metadata
                if sid in self.metadata:
                    self.metadata.pop(sid, None)
                # remove reverse map
                self.int_to_id.pop(int(int_id), None)
        if int_ids:
            try:
                self.index.remove_ids(np.array(int_ids, dtype="int64"))
            except Exception:
                logger.exception("Failed to remove ids from FAISS index")
                # continue and persist mapping changes anyway
            self._save_meta_and_index()

    def query(self, embedding, top_k=5, include_metadata=True):
        """
        input embedding: list[float] or numpy array
        returns dict similar shape: {'matches': [{'id': str, 'score': float, 'metadata': {...}}], ...}
        """
        if self.index is None or self.dim is None:
            return {"matches": []}
        vec = np.array(embedding, dtype="float32")
        if vec.ndim == 1:
            vec = vec.reshape(1, -1)
        if vec.shape[1] != self.dim:
            # try normalize or pad/truncate not supported
            raise ValueError(f"Query embedding dimension {vec.shape[1]} != index dim {self.dim}")
        # normalize for cosine (we stored normalized)
        norms = np.linalg.norm(vec, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vec = vec / norms
        try:
            D, I = self.index.search(vec, top_k)
        except Exception:
            logger.exception("FAISS search failed")
            return {"matches": []}
        matches = []
        for score, int_id in zip(D[0].tolist(), I[0].tolist()):
            if int_id == -1:
                continue
            sid = self.int_to_id.get(int(int_id))
            md = self.metadata.get(sid) if include_metadata else None
            matches.append({"id": sid, "score": float(score), "metadata": md})
        return {"matches": matches}
