import os
from .abc import StorageClient
from .local import LocalStorage

_storage_client = None

def get_storage_client() -> StorageClient:
    """
    Return a singleton StorageClient.
    Uses S3Storage if DATASET_S3_BUCKET or TRANSCRIBE_S3_BUCKET are configured and boto3 available,
    otherwise falls back to LocalStorage.
    """
    global _storage_client
    if _storage_client is not None:
        return _storage_client

    # prefer S3 if a bucket is configured
    bucket = os.getenv("DATASET_S3_BUCKET") or os.getenv("TRANSCRIBE_S3_BUCKET")
    if bucket:
        try:
            from .s3 import S3Storage
            region = os.getenv("AWS_DEFAULT_REGION")
            _storage_client = S3Storage(region_name=region)
            return _storage_client
        except Exception:
            # if S3 implementation fails to import/construct, fall back to local
            pass

    # fallback local
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "uploads")
    _storage_client = LocalStorage(base_dir=base)
    return _storage_client
