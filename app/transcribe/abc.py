from abc import ABC, abstractmethod

class Transcriber(ABC):
    """Abstract transcriber: implement transcribe_file that returns text transcript."""

    @abstractmethod
    def transcribe_file(self, file_path: str, language_code: str = "en-US") -> str:
        """
        Transcribe the given local audio file and return the transcript text.
        Implementations may upload the file (e.g., to S3) and call external services.
        """
        raise NotImplementedError
