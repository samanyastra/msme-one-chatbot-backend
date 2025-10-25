from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Any, Mapping, Optional

@dataclass
class Document:
    id: str
    text: str
    meta: Optional[Mapping[str, Any]] = None

class Retriever(ABC):
    """Responsible for returning candidate documents for a query."""
    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5) -> List[Document]:
        raise NotImplementedError

class Reader(ABC):
    """Responsible for producing an answer from documents + query context."""
    @abstractmethod
    def read(self, docs: List[Document], query: str) -> str:
        raise NotImplementedError

class RAGEngine(ABC):
    """High-level interface: given a query, returns an answer and used docs."""
    @abstractmethod
    def answer(self, query: str, top_k: int = 5) -> dict:
        """Return a dict: { 'answer': str, 'docs': List[Document] }"""
        raise NotImplementedError
