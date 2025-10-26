import logging
from multiprocessing import Process, set_start_method
import os

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
    Runs with its own Flask app context.
    """
    try:
        from app import create_app
        app = create_app()
        with app.app_context():
            from ..file_readers.impl import get_reader_for_extension
            from ..rag.service import index_document
            from ..models import Document
            from ..extensions import db

            # determine extension
            ext = os.path.splitext(file_path)[1].lstrip(".").lower()
            reader = get_reader_for_extension(ext)
            if reader is None:
                app.logger.error("No reader for extension: %s", ext)
                raise RuntimeError(f"No reader available for .{ext} files")

            # read text
            try:
                text = reader.read_text(file_path) or ""
            except Exception as e:
                app.logger.exception("Failed to read uploaded file %s: %s", file_path, e)
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
        # allow exception to propagate to child process exit for visibility
        raise

def start_index_process(doc_id):
    # prefer spawn to avoid issues on some platforms
    try:
        set_start_method("spawn", force=False)
    except RuntimeError:
        # start method already set
        pass
    p = Process(target=_worker_index, args=(doc_id,), daemon=True)
    p.start()
    logger.info("Started index process pid=%s for doc_id=%s", p.pid, doc_id)
    return p.pid

def start_delete_process(doc_id):
    try:
        set_start_method("spawn", force=False)
    except RuntimeError:
        pass
    p = Process(target=_worker_delete, args=(doc_id,), daemon=True)
    p.start()
    logger.info("Started delete process pid=%s for doc_id=%s", p.pid, doc_id)
    return p.pid

def start_file_process(doc_id, file_path):
    """
    Start a separate process to read 'file_path' and index the document.
    """
    try:
        set_start_method("spawn", force=False)
    except RuntimeError:
        pass
    p = Process(target=_worker_process_file, args=(doc_id, file_path), daemon=True)
    p.start()
    logger.info("Started file-processing process pid=%s for doc_id=%s file=%s", p.pid, doc_id, file_path)
    return p.pid
