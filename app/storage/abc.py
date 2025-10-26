from abc import ABC, abstractmethod

class StorageClient(ABC):
    """Abstract storage client used to upload and download files."""

    @abstractmethod
    def upload_fileobj(self, fileobj, bucket: str, key: str) -> str:
        """
        Upload a file-like object to storage.

        Returns a URI (e.g. s3://bucket/key or file:///path/to/file).
        """
        raise NotImplementedError

    @abstractmethod
    def download_to_path(self, uri: str, dest_path: str) -> str:
        """
        Download the object identified by `uri` to local dest_path.
        Returns the local path on success.
        """
        raise NotImplementedError
