from typing import List
from .abc import Document, Retriever, Reader, RAGEngine

class InMemoryRetriever(Retriever):
    def __init__(self, docs: List[Document]):
        self.docs = docs

    def retrieve(self, query: str, top_k: int = 5) -> List[Document]:
        # naive substring scoring: return docs that contain any token, ordered by length match
        q = query.lower().strip()
        if not q:
            return []
        tokens = [t for t in q.split() if t]
        scored = []
        for d in self.docs:
            text = (d.text or "").lower()
            score = sum(1 for t in tokens if t in text)
            if score > 0:
                scored.append((score, d))
        scored.sort(key=lambda x: (-x[0], len(x[1].text)))
        return [d for _, d in scored[:top_k]]

class SimpleReader(Reader):
    def read(self, docs: List[Document], query: str) -> str:
        # naive reader: join the top doc snippets and echo a simple template answer
        if not docs:
            return "I couldn't find relevant information."
        snippets = []
        for d in docs:
            text = d.text.strip()
            snippets.append(f"- {text[:300]}{'...' if len(text) > 300 else ''}")
        context = "\n".join(snippets)
        return f"Answer (based on {len(docs)} doc(s)):\n{context}"

class InMemoryRAG(RAGEngine):
    def __init__(self, docs: List[Document]):
        self.retriever = InMemoryRetriever(docs)
        self.reader = SimpleReader()

    def answer(self, query: str, top_k: int = 5) -> dict:
        docs = self.retriever.retrieve(query, top_k=top_k)
        answer = self.reader.read(docs, query)
        return {"answer": answer, "docs": docs}
