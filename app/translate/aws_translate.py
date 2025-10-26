import os
import logging
from typing import Optional
import boto3
import botocore
from .abc import Translator

logger = logging.getLogger(__name__)

class AwsTranslator(Translator):
    """
    Simple AWS Translate wrapper.

    Use SOURCE_LANGUAGE_CODE='auto' when source_lang is None (AWS supports auto-detect).
    """

    def __init__(self, region_name: Optional[str] = None, aws_access_key_id: Optional[str] = None, aws_secret_access_key: Optional[str] = None):
        client_kwargs = {}
        if region_name:
            client_kwargs["region_name"] = region_name
        if aws_access_key_id and aws_secret_access_key:
            client_kwargs["aws_access_key_id"] = aws_access_key_id
            client_kwargs["aws_secret_access_key"] = aws_secret_access_key
        self.client = boto3.client("translate", **client_kwargs)

    def _short_lang(self, lang: Optional[str]) -> Optional[str]:
        if not lang:
            return None
        # normalize like "te-IN" -> "te"
        try:
            return lang.split("-")[0].lower()
        except Exception:
            return lang

    def translate_text(self, text: str, source_lang: Optional[str] = None, target_lang: str = "en") -> str:
        if not text:
            return ""
        src = self._short_lang(source_lang) or "auto"
        try:
            resp = self.client.translate_text(
                Text=text,
                SourceLanguageCode=src,
                TargetLanguageCode=target_lang
            )
            return resp.get("TranslatedText", "") or ""
        except botocore.exceptions.BotoCoreError:
            logger.exception("AWS Translate failed")
            return text
        except Exception:
            logger.exception("Translate error")
            return text
