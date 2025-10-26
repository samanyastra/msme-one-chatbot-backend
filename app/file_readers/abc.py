from abc import ABC, abstractmethod

class FileReader(ABC):
    """Abstract file reader that extracts plain text from an uploaded file."""

    @abstractmethod
    def read_text(self, file_path: str) -> str:
        """
        Given a local file path, return the extracted text as a string.
        Implementations should raise a clear Exception on failure.
        """
        raise NotImplementedError
