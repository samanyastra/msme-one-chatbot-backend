def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64):
    """
    Naive chunker: split text into whitespace tokens and create chunks of approximate chunk_size tokens.
    Returns list of chunk strings.
    """
    if not text:
        return []
    tokens = text.split()
    chunks = []
    i = 0
    while i < len(tokens):
        chunk_tokens = tokens[i:i + chunk_size]
        chunks.append(" ".join(chunk_tokens))
        i += chunk_size - overlap
    return chunks
