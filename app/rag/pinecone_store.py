import os
import logging
from pinecone import Pinecone
logger = logging.getLogger(__name__)
class PineconeStore:


    def __init__(self) -> None:
        api_key = os.environ.get('PINECONE_API_KEY')
        self.index_host = os.environ.get('PINECONE_INDEX_HOST', None)
        self.batch_limit = 95
        pc = Pinecone(api_key=api_key)
        self.index = pc.Index(host=self.index_host)

        if (api_key is None) or (self.index is None):
           
            logger.exception("Missing Pinecone configuration: PINECONE_API_KEY or PINECONE_INDEX_HOST not set")
            raise RuntimeError("Pinecone configuration missing: set PINECONE_API_KEY and PINECONE_INDEX_HOST")
        

    def _upsert_in_batch(self, vectors):
        for i in range(0, len(vectors), self.batch_limit ):
            vec_list = vectors[i:self.batch_limit+1]
            logger.exception(str(vec_list))
            self.index.upsert(vec_list)
    
    def upsert_vectors(self, vectors):
        self.index.upsert_records("__default__",vectors)
