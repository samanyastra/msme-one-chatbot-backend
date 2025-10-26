import os
import logging
from urllib.parse import urlparse
import botocore
import boto3
from .abc import StorageClient

logger = logging.getLogger(__name__)

class S3Storage(StorageClient):
    def __init__(self, region_name: str = None):
        client_kwargs = {}
        if region_name:
            client_kwargs["region_name"] = region_name
        # boto3 will read creds from env / instance profile / shared config
        self.s3 = boto3.client("s3", **client_kwargs)
        # optional default bucket from env
        self.default_bucket = os.getenv("DATASET_S3_BUCKET") or os.getenv("TRANSCRIBE_S3_BUCKET")

    def ensure_bucket(self, bucket: str):
        try:
            self.s3.head_bucket(Bucket=bucket)
        except botocore.exceptions.ClientError as e:
            code = None
            try:
                code = int(e.response.get("Error", {}).get("Code", 0))
            except Exception:
                pass
            # try create if not found (requires proper IAM)
            try:
                create_kwargs = {"Bucket": bucket}
                region = self.s3.meta.region_name
                if region and region != "us-east-1":
                    create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
                self.s3.create_bucket(**create_kwargs)
                logger.info("Created S3 bucket %s", bucket)
            except Exception:
                logger.exception("Failed to create or access bucket %s", bucket)
                raise

    def upload_fileobj(self, fileobj, bucket: str, key: str) -> str:
        if not bucket:
            bucket = self.default_bucket
        if not bucket:
            raise RuntimeError("No S3 bucket configured for upload")
        # ensure bucket exist
        self.ensure_bucket(bucket)
        # ensure fileobj positioned
        try:
            fileobj.seek(0)
        except Exception:
            pass
        try:
            self.s3.upload_fileobj(fileobj, bucket, key)
            return f"s3://{bucket}/{key}"
        except Exception:
            logger.exception("S3 upload failed for s3://%s/%s", bucket, key)
            raise

    def download_to_path(self, uri: str, dest_path: str) -> str:
        parsed = urlparse(uri)
        if parsed.scheme != "s3":
            raise ValueError("S3Storage.download_to_path expects s3:// URI")
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        try:
            self.s3.download_file(bucket, key, dest_path)
            return dest_path
        except Exception:
            logger.exception("Failed to download s3://%s/%s to %s", bucket, key, dest_path)
            raise
