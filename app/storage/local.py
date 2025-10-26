import os
import shutil
import pathlib
from .abc import StorageClient

class LocalStorage(StorageClient):
    def __init__(self, base_dir: str = None):
        base = base_dir or os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "uploads")
        os.makedirs(base, exist_ok=True)
        self.base = base

    def upload_fileobj(self, fileobj, bucket: str, key: str) -> str:
        # bucket ignored for local store; key used as filename under base
        fname = os.path.basename(key)
        dest = os.path.join(self.base, fname)
        try:
            # ensure fileobj at start
            try:
                fileobj.seek(0)
            except Exception:
                pass
            with open(dest, "wb") as fh:
                shutil.copyfileobj(fileobj, fh)
            return f"file://{os.path.abspath(dest)}"
        except Exception:
            raise

    def download_to_path(self, uri: str, dest_path: str) -> str:
        # accept file:// URIs or direct local paths
        if uri.startswith("file://"):
            src = uri[len("file://"):]
        else:
            src = uri
        shutil.copyfile(src, dest_path)
        return dest_path
