from abc import ABC, abstractmethod
from typing import Optional

class Translator(ABC):
    """Translate text to a target language (default 'en')."""

    @abstractmethod
    def translate_text(self, text: str, source_lang: Optional[str] = None, target_lang: str = "en") -> str:
        """
        Translate `text` from source_lang (if provided) to target_lang and return translated text.
        """
        raise NotImplementedError
