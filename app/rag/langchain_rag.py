from typing import List, Optional
import logging
import os
import threading

from .abc import RAGEngine, Document as RAGDocument
from .chunker import chunk_text

logger = logging.getLogger(__name__)

# lazy import of heavy langchain modules to avoid import-time overhead
def _import_langchain():
    """
    Robust import helper for LangChain components across versions.
    Tries known module paths for HuggingFaceEmbeddings and FAISS and returns (HuggingFaceEmbeddings, FAISS).
    Raises a clear exception if none of the import attempts succeed.
    """
    # try the newer (namespaced) location first
    try:
        from langchain.embeddings.huggingface import HuggingFaceEmbeddings  
        from langchain_community.vectorstores import FAISS
        return HuggingFaceEmbeddings, FAISS
    except Exception:
        pass

    # try the older flat location
    try:
        from langchain.embeddings import HuggingFaceEmbeddings  # older langchain versions
        from langchain_community.vectorstores import FAISS
        return HuggingFaceEmbeddings, FAISS
    except Exception:
        pass

    # final attempt: some releases expose huggingface under embeddings.huggingface_transformers
    try:
        from langchain.embeddings.huggingface_transformers import HuggingFaceEmbeddings
        from langchain.vectorstores import FAISS
        return HuggingFaceEmbeddings, FAISS
    except Exception as e:
        logger.exception("LangChain embedding imports failed: %s", e)
        raise ImportError(
            "Could not import HuggingFaceEmbeddings or FAISS from langchain. "
            "Ensure a compatible langchain version is installed. "
            "You can install LangChain + HF support with: pip install 'langchain[hub,faiss]' "
            "or install a compatible langchain + transformers version."
        )

class LangchainFaissRAG(RAGEngine):
    """
    Simple LangChain + FAISS RAG engine:

    - Builds a LangChain FAISS vectorstore from Document rows (chunks + metadata) on first use.
    - Uses HuggingFaceEmbeddings (default intfloat/e5-base-v2) for embeddings.
    - For queries, retrieves top_k chunks and returns them as RAGDocument dataclasses and a joined answer.
    """
    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or os.getenv("SENTENCE_TRANSFORMER_MODEL", "intfloat/e5-base-v2")
        self._embeddings = None
        self._vectorstore = None
        self._built = False
        self._building = False
        self._build_lock = threading.Lock()

    def _ensure_embeddings(self):
        if self._embeddings is None:
            HuggingFaceEmbeddings, _ = _import_langchain()
            # HuggingFaceEmbeddings will use sentence-transformers model under the hood when model_name is a HF id
            self._embeddings = HuggingFaceEmbeddings(model_name=self.model_name)

    def _build_vectorstore(self, app=None):
        """
        Build FAISS vectorstore from Document rows (DB access expected to be inside app context).
        If `app` is provided, use its app_context() in the background thread.
        """
        # idempotent build (protected by lock)
        with self._build_lock:
            if self._built or self._building:
                return
            self._building = True
        try:
            # ensure langchain imports / embeddings
            HuggingFaceEmbeddings, FAISS = _import_langchain()
            self._ensure_embeddings()

            # use provided app context if given, otherwise try current_app
            if app is not None:
                # run DB work inside the provided app context
                with app.app_context():
                    from ..models import Document
                    docs = Document.query.order_by(Document.created_at.asc()).all()
            else:
                try:
                    from flask import current_app
                    with current_app.app_context():
                        from ..models import Document
                        docs = Document.query.order_by(Document.created_at.asc()).all()
                except RuntimeError:
                    logger.error("No Flask application context available to build vectorstore - aborting build.")
                    self._vectorstore = None
                    self._built = True
                    return

            texts = []
            metadatas = []
            for d in docs:
                doc_text = (d.text or "").strip()
                if not doc_text:
                    continue
                chunks = chunk_text(doc_text, chunk_size=512, overlap=64)
                for idx, ch in enumerate(chunks):
                    texts.append(ch)
                    metadatas.append({"doc_id": d.id, "title": d.title, "chunk_index": idx, "chunk_text": ch})

            if not texts:
                # create empty vectorstore placeholder
                self._vectorstore = None
                self._built = True
                return

            # build vectorstore (in-memory FAISS). Persisting can be added later.
            self._vectorstore = FAISS.from_texts(texts=texts, embedding=self._embeddings, metadatas=metadatas)
            logger.info("LangChain FAISS vectorstore built with %d chunks", len(texts))
            self._built = True
        except Exception:
            logger.exception("Failed to build LangChain FAISS vectorstore")
            self._vectorstore = None
            self._built = True  # avoid repeated failing attempts
        finally:
            self._building = False

    def start_background_build(self, app=None):
        """Start the vectorstore build in a background thread (non-blocking). Accept optional Flask app."""
        if self._built or self._building:
            return
        t = threading.Thread(target=self._build_vectorstore, args=(app,), daemon=True)
        t.start()

    def is_ready(self) -> bool:
        """Return True if the vectorstore has been built and is usable."""
        return self._built and (self._vectorstore is not None)

    def set_vectorstore(self, vectorstore):
        """
        Inject a pre-built LangChain FAISS vectorstore instance.
        Use this from your background/reindex process after building the index.
        """
        self._vectorstore = vectorstore
        self._built = True

    def answer(self, query: str, top_k: int = 3) -> dict:
        """
        Retrieval-only: do not build or reindex here.
        If the vectorstore is not provided, return an explicit message instructing to run indexing.
        """
        if not query or not query.strip():
            return {"answer": "Empty query", "docs": []}

        # Do not attempt to build here. Require a pre-built vectorstore.
        if not self._vectorstore:
            return {
                "answer": "No index available. Please run the indexing process (reindex) before querying.",
                "docs": []
            }

        docs: List[RAGDocument] = []
        snippets = []

        try:
            retriever = self._vectorstore.as_retriever(search_kwargs={"k": top_k})
            results = retriever.get_relevant_documents(query)
            for r in results:
                meta = dict(r.metadata or {})
                text = r.page_content or ""
                docs.append(RAGDocument(id=str(meta.get("doc_id", "")), text=text, meta=meta))
                snippets.append(text.strip())
        except Exception:
            logger.exception("LangChain retrieval failed")
            return {"answer": "Retrieval failed", "docs": []}

        if snippets:
            answer = "Retrieved excerpts:\n\n" + "\n\n---\n\n".join(snippets[:min(len(snippets), top_k)])
        else:
            answer = "No relevant content found."

        return {"answer": answer, "docs": docs}
