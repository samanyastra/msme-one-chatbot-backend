# from torch import embedding
from ..models import Document
from ..extensions import db
from .chunker import chunk_text
from .embeddings import EmbeddingProvider
# from .faiss_store import FaissStore  # ...changed import...
from .pinecone_store import PineconeStore
import os
import uuid
import logging

logger = logging.getLogger(__name__)


# lazy singletons
_embedder = None
_vector_store = None  # was _pinecone

def get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingProvider()
    return _embedder

def get_vector_store():
    global _vector_store
    if _vector_store is None:
        _vector_store = PineconeStore()
    return _vector_store

def index_document(doc_id: int):
    """
    Chunk -> embed -> upsert vectors -> update Document.vector_ids
    """
    doc = Document.query.get(doc_id)
    if not doc:
        raise ValueError("document not found")
    chunks = chunk_text(doc.text or "", chunk_size=1024, overlap=64)
    if not chunks:
        return {"status": "no-chunks"}
    # embedder = get_embedder()
    # embeddings = embedder.embed(chunks)
    embeddings = [i for i in range(len(chunks))]
    vectors = []
    vector_ids = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        vid = f"{doc.id}_{uuid.uuid4().hex}_{i}"
        # vectors.append({"id": vid, "values": emb, "metadata": {"doc_id": doc.id, "chunk_index": i, "chunk_text": chunk}})
        # vectors.append({"id": vid, "values": chunk, "metadata": {"doc_id": doc.id, "doc_name": doc.filenam, "chunk_index": i, "chunk_text": chunk}})
        vobj = {
            "_id": vid,
            "text": chunk,
            "doc_id": doc.id, 
            "doc_name": doc.filename, 
            "chunk_index": i,
            # "metadata": {"doc_id": doc.id, "doc_name": doc.filename, "chunk_index": i}
        }
        vector_ids.append(vid)
        vectors.append(vobj)
    store = get_vector_store()
    store.upsert_vectors(vectors)
    # update document metadata
    doc.vector_ids = vector_ids
    db.session.add(doc)
    db.session.commit()
    return {"status": "indexed", "vector_count": len(vector_ids)}

def delete_document_vectors(doc_id: int):
    doc = Document.query.get(doc_id)
    if not doc:
        return {"status": "not-found"}
    ids = doc.vector_ids or []
    if ids:
        store = get_vector_store()
        store.delete_vectors(ids)
    doc.vector_ids = []
    db.session.add(doc)
    db.session.commit()
    return {"status": "deleted", "deleted_count": len(ids)}
