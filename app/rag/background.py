import logging
from multiprocessing import Process, set_start_method
import tempfile
import os
import boto3
import shutil
from urllib.parse import urlparse
import multiprocessing as mp
import warnings
import re


logger = logging.getLogger(__name__)

def _worker_index(doc_id):
    # create a fresh app in the child process so DB/Flask-SQLAlchemy can be used safely
    from app import create_app
    app = create_app()
    with app.app_context():
        # allow this specific RuntimeError to bubble up so the process exits with error
        try:
            from .service import index_document
            index_document(doc_id)
        except RuntimeError as re:
            # if it's the pinecone-client missing error, re-raise so it's visible in process exit
            if "pinecone-client not installed" in str(re):
                logger.exception("Pinecone client missing; re-raising to fail worker")
                raise
            # otherwise log and continue (or allow to be handled as below)
            logger.exception("Runtime error in index worker for doc_id=%s: %s", doc_id, re)
            raise
        except Exception:
            logger.exception("background index worker failed for doc_id=%s", doc_id)
            # keep exception allowed to bubble to terminate the child process
            raise

def _worker_delete(doc_id):
    from app import create_app
    app = create_app()
    with app.app_context():
        try:
            from .service import delete_document_vectors
            delete_document_vectors(doc_id)
        except Exception:
            logger.exception("background delete worker failed for doc_id=%s", doc_id)
            # re-raise to fail the child process if necessary
            raise

def _worker_process_file(doc_id, file_path):
    """
    Child-process worker: read file contents, update Document.text and run index_document.
    Accepts either a local path or an S3 URI (s3://bucket/key). Downloads S3 objects to a temp file.
    """
    tmp_path = None
    try:
        from app import create_app
        app = create_app()
        with app.app_context():
            from ..file_readers.impl import get_reader_for_extension
            from ..rag.service import index_document
            from ..models import Document
            from ..extensions import db

            local_path = file_path
            # If S3 URI provided, download to temporary file
            if isinstance(file_path, str) and file_path.lower().startswith("s3://"):
                parsed = urlparse(file_path)
                bucket = parsed.netloc
                key = parsed.path.lstrip("/")
                s3 = boto3.client("s3")
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(key)[1] or "")
                tmp_path = tmp.name
                tmp.close()
                try:
                    s3.download_file(bucket, key, tmp_path)
                    local_path = tmp_path
                except Exception:
                    app.logger.exception("Failed to download %s from S3", file_path)
                    raise

            # determine extension
            ext = os.path.splitext(local_path)[1].lstrip(".").lower()
            reader = get_reader_for_extension(ext)
            if reader is None:
                app.logger.error("No reader for extension: %s", ext)
                raise RuntimeError(f"No reader available for .{ext} files")

            # read text
            try:
                text = reader.read_text(local_path) or ""
            except Exception:
                app.logger.exception("Failed to read uploaded file %s", local_path)
                raise

            # update document record
            doc = Document.query.get(doc_id)
            if not doc:
                app.logger.error("Document not found for id=%s", doc_id)
                return
            doc.text = text
            db.session.add(doc)
            db.session.commit()

            # run indexing (existing logic)
            index_document(doc_id)
    except Exception:
        logger.exception("background file processing worker failed for doc_id=%s", doc_id)
        raise
    finally:
        # cleanup temp file if we downloaded to it
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                logger.debug("Failed to remove temporary file %s", tmp_path)

# suppress the known resource_tracker semaphore-leak warning emitted at shutdown
# This only suppresses the specific text from resource_tracker and does not hide other warnings.


# use a dedicated spawn context rather than calling set_start_method repeatedly.
_spawn_ctx = mp.get_context("spawn")

def start_index_process(doc_id):
    """
    Start indexing in a separate OS process (spawn context) to avoid blocking and
    to avoid resource leaks associated with repeated global start_method calls.
    """
    p = _spawn_ctx.Process(target=_worker_index, args=(doc_id,), daemon=True)
    p.start()
    logger.info("Started index process pid=%s for doc_id=%s", p.pid, doc_id)
    return p.pid

def start_delete_process(doc_id):
    p = _spawn_ctx.Process(target=_worker_delete, args=(doc_id,), daemon=True)
    p.start()
    logger.info("Started delete process pid=%s for doc_id=%s", p.pid, doc_id)
    return p.pid

def start_file_process(doc_id, file_path):
    """
    Start a separate process to read 'file_path' (local path or s3://...) and index the document.
    """
    p = _spawn_ctx.Process(target=_worker_process_file, args=(doc_id, file_path), daemon=True)
    p.start()
    logger.info("Started file-processing process pid=%s for doc_id=%s file=%s", p.pid, doc_id, file_path)
    return p.pid
