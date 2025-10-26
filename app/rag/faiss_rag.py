import logging
from typing import List
from .embeddings import EmbeddingProvider
from .faiss_store import FaissStore
from .abc import Document as RAGDocument, RAGEngine

logger = logging.getLogger(__name__)

class FaissRAG(RAGEngine):
    """
    Simple RAG engine using an embedding provider and the local FaissStore.
    It embeds the query, queries the vector store, and returns matched chunks as Documents.
    """
    def __init__(self, embedder: EmbeddingProvider = None, store: FaissStore = None):
        self.embedder = embedder or EmbeddingProvider()
        self.store = store or FaissStore()

    def answer(self, query: str, top_k: int = 5) -> dict:
        if not query or not query.strip():
            return {"answer": "empty query", "docs": []}

        # get embedding for the single query
        emb = self.embedder.embed(query)
        # embed may return list for single input in some implementations; normalize to 1-D list
        if isinstance(emb, list) and len(emb) and isinstance(emb[0], list):
            embedding = emb[0]
        else:
            embedding = emb

        # query faiss store
        resp = self.store.query(embedding, top_k=top_k, include_metadata=True) or {}
        matches = resp.get("matches", [])

        docs: List[RAGDocument] = []
        snippets = []
        for m in matches:
            meta = m.get("metadata") or {}
            chunk_text = meta.get("chunk_text") or ""
            doc_id = meta.get("doc_id") or meta.get("docId") or m.get("id")
            # create rag Document dataclass (id as string)
            docs.append(RAGDocument(id=str(doc_id), text=chunk_text, meta=meta))
            if chunk_text:
                snippets.append(chunk_text[:400])

        # simple reader: join snippets to form an answer
        if snippets:
            answer = "Relevant excerpts:\n" + "\n\n".join(snippets[:min(len(snippets), 5)])
        else:
            answer = "No relevant content found."

        return {"answer": answer, "docs": docs}
