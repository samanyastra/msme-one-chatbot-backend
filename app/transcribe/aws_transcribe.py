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

    If language_code is None, this implementation will ask AWS Transcribe to auto-detect
    the language (IdentifyLanguage=True). If a language_code is provided, it will be
    normalized and passed explicitly. Fallbacks are applied on failures.
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

    def transcribe_file(self, file_path: str, language_code: str = None, timeout: int = 300) -> str:
        """
        Upload file to S3, start a Transcribe job, poll until completion, return transcript text.

        If language_code is None -> request AWS to identify language automatically
        (IdentifyLanguage=True). If language_code is provided, it will be normalized
        to an AWS language code and used directly.

        Returns the transcript text. Raises on fatal errors.
        """
        def _normalize_language_code(code: str) -> str:
            if not code:
                raise ValueError("language_code is required")
            s = code.strip().lower()
            mapping = {
                # English variants
                "english": "en-US", "en": "en-US", "en-us": "en-US", "en_us": "en-US", "en-gb": "en-GB", "en_gb": "en-GB",
                # Indian languages commonly encountered
                "telugu": "te-IN", "te": "te-IN", "te-in": "te-IN", "te_in": "te-IN",
                "hindi": "hi-IN", "hi": "hi-IN", "hi-in": "hi-IN",
                "marathi": "mr-IN", "mr": "mr-IN", "mr-in": "mr-IN",
                "tamil": "ta-IN", "ta": "ta-IN", "ta-in": "ta-IN",
                "kannada": "kn-IN", "kn": "kn-IN", "kn-in": "kn-IN",
                "malayalam": "ml-IN", "ml": "ml-IN", "ml-in": "ml-IN",
                "bengali": "bn-IN", "bn": "bn-IN", "bn-in": "bn-IN",
            }
            if s in mapping:
                return mapping[s]
            # Accept and normalize codes like "en-us", "en_US", "en-US"
            normalized = s.replace("_", "-")
            if "-" in normalized:
                lang, region = normalized.split("-", 1)
                return f"{lang.lower()}-{region.upper()}"
            # Fallback: if it's just a 2-letter code, map to a sensible default region (US)
            if len(normalized) == 2:
                return f"{normalized.lower()}-US"
            # Otherwise return as-is (let AWS validate)
            return code

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

        # start job: either identify language automatically, or use provided language_code
        logger.info("Starting Transcribe job %s for %s (language_code=%s)", job_name, media_uri, language_code)
        try:
            if not language_code:
                # Ask AWS to identify language automatically
                start_kwargs = {
                    "TranscriptionJobName": job_name,
                    "Media": {"MediaFileUri": media_uri},
                    "MediaFormat": ext,
                    "IdentifyLanguage": True,
                }
                # Optionally you can provide LanguageOptions to hint AWS, omitted here to let it fully auto-detect
                start_resp = self.transcribe.start_transcription_job(**start_kwargs)
            else:
                aws_lang = _normalize_language_code(language_code)
                logger.info("Using language code '%s' for input '%s'", aws_lang, language_code)
                start_resp = self.transcribe.start_transcription_job(
                    TranscriptionJobName=job_name,
                    Media={"MediaFileUri": media_uri},
                    MediaFormat=ext,
                    LanguageCode=aws_lang,
                )
        except botocore.exceptions.ClientError as e:
            logger.exception("start_transcription_job failed with error")
            # If IdentifyLanguage approach failed and we had a language_code fallback, raise.
            # If IdentifyLanguage failed and we did not specify a language, try with a sensible default (en-US).
            if not language_code:
                try:
                    logger.info("Retrying transcription with default language en-US after IdentifyLanguage failure")
                    start_resp = self.transcribe.start_transcription_job(
                        TranscriptionJobName=job_name + "_retry",
                        Media={"MediaFileUri": media_uri},
                        MediaFormat=ext,
                        LanguageCode="en-US",
                    )
                except Exception:
                    logger.exception("Retry with default language failed")
                    raise
            else:
                raise

        # determine the transcription job name we started (handle retry case)
        transcription_job_name = None
        if 'start_resp' in locals() and isinstance(start_resp, dict):
            transcription_job_name = start_resp.get("TranscriptionJob", {}).get("TranscriptionJobName", job_name)
        else:
            transcription_job_name = job_name

        # poll for completion
        start_time = time.time()
        while True:
            try:
                status_resp = self.transcribe.get_transcription_job(TranscriptionJobName=transcription_job_name)
            except botocore.exceptions.ClientError:
                logger.exception("get_transcription_job failed")
                raise

            job = status_resp.get("TranscriptionJob", {})
            status = job.get("TranscriptionJobStatus")
            if status in ("COMPLETED", "FAILED"):
                break
            if time.time() - start_time > timeout:
                # optionally stop job (not implemented)
                raise TimeoutError(f"Transcription job {transcription_job_name} timed out after {timeout}s")
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
            return {"input_lang": None, "text": ""}

        text = transcripts[0].get("transcript", "")

        # try to determine detected language from the job info if available
        detected_lang = None
        try:
            # job variable exists in this scope above (from polling); attempt several common keys
            if isinstance(job, dict):
                detected_lang = job.get("LanguageCode") or \
                                (job.get("IdentifyLanguageResult") or {}).get("IdentifiedLanguage") or \
                                (job.get("IdentifyLanguageResult") or {}).get("LanguageCode")
                # Normalize simple forms if needed
                if isinstance(detected_lang, dict):
                    detected_lang = detected_lang.get("LanguageCode") or detected_lang.get("Language")
        except Exception:
            detected_lang = None

        return {"input_lang": detected_lang, "text": text}

