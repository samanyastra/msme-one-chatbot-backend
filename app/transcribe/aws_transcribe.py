import os
import uuid
import time
import json
import logging
import boto3
import botocore
import requests
from .abc import Transcriber

logger = logging.getLogger(__name__)

class AwsTranscriber(Transcriber):
    """
    AWS Transcribe implementation.

    Requires:
      - S3 bucket name (bucket must exist and Transcribe service can read it)
      - AWS credentials in environment or instance profile
    Configure via environment variable TRANSCRIBE_S3_BUCKET. Optionally set AWS_REGION.
    """

    def __init__(self, s3_bucket: str, region_name: str = None, aws_access_key_id: str = None, aws_secret_access_key: str = None):
        if not s3_bucket:
            raise ValueError("s3_bucket is required for AwsTranscriber")
        self.bucket = s3_bucket
        self.region = region_name or os.getenv("AWS_DEFAULT_REGION")
        client_kwargs = {}
        if self.region:
            client_kwargs["region_name"] = self.region
        if aws_access_key_id and aws_secret_access_key:
            client_kwargs["aws_access_key_id"] = aws_access_key_id
            client_kwargs["aws_secret_access_key"] = aws_secret_access_key

        self.s3 = boto3.client("s3", **client_kwargs)
        self.transcribe = boto3.client("transcribe", **client_kwargs)

    def _upload_to_s3(self, src_path: str, key: str):
        self.s3.upload_file(src_path, self.bucket, key)

    def transcribe_file(self, file_path: str, language_code: str = "en-US", timeout: int = 300) -> str:
        """
        Upload file to S3, start a Transcribe job, poll until completion, return transcript text.
        timeout seconds for job completion (default 300s).
        """
        basename = os.path.basename(file_path)
        ext = os.path.splitext(basename)[1].lstrip(".").lower() or "webm"
        key = f"transcribe_uploads/{uuid.uuid4().hex}.{ext}"
        job_name = f"transcribe_job_{uuid.uuid4().hex}"

        # upload
        logger.info("Uploading %s to s3://%s/%s", file_path, self.bucket, key)
        try:
            self._upload_to_s3(file_path, key)
        except botocore.exceptions.BotoCoreError:
            logger.exception("S3 upload failed")
            raise

        media_uri = f"s3://{self.bucket}/{key}"

        # start job
        logger.info("Starting Transcribe job %s for %s", job_name, media_uri)
        try:
            start_resp = self.transcribe.start_transcription_job(
                TranscriptionJobName=job_name,
                Media={"MediaFileUri": media_uri},
                MediaFormat=ext,
                LanguageCode=language_code,
                # Settings optional: e.g., ShowSpeakerLabels, MaxSpeakerLabels, VocabularyName
            )
        except botocore.exceptions.ClientError:
            logger.exception("start_transcription_job failed")
            raise

        # poll for completion
        start_time = time.time()
        while True:
            try:
                status_resp = self.transcribe.get_transcription_job(TranscriptionJobName=job_name)
            except botocore.exceptions.ClientError:
                logger.exception("get_transcription_job failed")
                raise

            job = status_resp.get("TranscriptionJob", {})
            status = job.get("TranscriptionJobStatus")
            if status in ("COMPLETED", "FAILED"):
                break
            if time.time() - start_time > timeout:
                # optionally stop job (not implemented)
                raise TimeoutError(f"Transcription job {job_name} timed out after {timeout}s")
            time.sleep(3)

        if job.get("TranscriptionJobStatus") != "COMPLETED":
            reason = job.get("FailureReason", "unknown")
            logger.error("Transcription job failed: %s", reason)
            raise RuntimeError(f"Transcription failed: {reason}")

        transcript_uri = job.get("Transcript", {}).get("TranscriptFileUri")
        if not transcript_uri:
            raise RuntimeError("No transcript URI returned by Transcribe")

        # fetch transcript json
        logger.info("Fetching transcript JSON from %s", transcript_uri)
        resp = requests.get(transcript_uri, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        # expected structure: results -> transcripts[0] -> transcript
        transcripts = body.get("results", {}).get("transcripts", [])
        if not transcripts:
            return ""
        text = transcripts[0].get("transcript", "")
        return text
