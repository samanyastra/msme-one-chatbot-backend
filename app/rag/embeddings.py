import os
import logging

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    _HAS_SBT = True
except Exception:
    _HAS_SBT = False

class EmbeddingProvider:
    def __init__(self, model_name: str = None):
        """
        Prefer intfloat/e5-base-v2 (E5); if unavailable try environment override,
        then fall back to all-MiniLM-L6-v2. If none load, use deterministic fallback.
        """
        self.model = None
        self.model_name = None

        if not _HAS_SBT:
            logger.info("sentence-transformers not available; will use deterministic fallback")
            return

        # Build priority list: prefer E5, then env override, then MiniLM
        env_model = os.getenv("SENTENCE_TRANSFORMER_MODEL")
        candidates = []
        # if explicit param provided, respect it after E5 preference
        if model_name:
            candidates.append(model_name)
        # prefer E5 first
        candidates.insert(0, "intfloat/e5-base-v2")
        # env override next (avoid duplicates)
        if env_model and env_model not in candidates:
            candidates.append(env_model)
        # final fallback
        if "all-MiniLM-L6-v2" not in candidates:
            candidates.append("all-MiniLM-L6-v2")

        # Try to load the first model that succeeds
        for m in candidates:
            try:
                logger.info("Attempting to load sentence-transformers model: %s", m)
                self.model = SentenceTransformer(m)
                self.model_name = m
                logger.info("Loaded embedding model: %s", m)
                break
            except Exception:
                logger.exception("Failed to load model %s; trying next", m)
                self.model = None
                self.model_name = None

        if not self.model:
            logger.warning("No sentence-transformers model loaded; embedding will use deterministic fallback")

    def embed(self, texts):
        """
        texts: str | list[str] -> list[list[float]] (returns single vector if input was str)
        """
        single = False
        if isinstance(texts, str):
            texts = [texts]
            single = True

        # Use loaded model if available
        if self.model:
            try:
                arr = self.model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
                # arr may be numpy array; convert to python list of lists
                result = [list(v) for v in arr]
                return result[0] if single else result
            except Exception:
                logger.exception("Model encoding failed; falling back to deterministic embedding")

        # Deterministic fallback embedding (fast, non-semantic)
        out = []
        for t in texts:
            h = abs(hash(t))
            vec = []
            dim = 128
            for i in range(dim):
                vec.append(((h >> (i % 64)) & 0xFF) / 255.0)
            out.append(vec)
        return out[0] if single else out
