import os
import json
import logging

logger = logging.getLogger(__name__)

class BedrockClient:
    """
    Minimal Bedrock runtime client wrapper.

    Usage:
      bc = BedrockClient(model_id=os.getenv("BEDROCK_MODEL_ID"))
      text = bc.generate(prompt, max_tokens=2000)
    """
    def __init__(self, model_id: str = None, region: str = None):
        self.model_id = model_id or os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
        self.region = region or os.getenv("AWS_DEFAULT_REGION")
        try:
            import boto3  # local import so module optional
            kwargs = {}
            if self.region:
                kwargs["region_name"] = self.region
            self.client = boto3.client("bedrock-runtime", **kwargs)
        except Exception as e:
            logger.exception("Failed to initialize boto3 bedrock-runtime client: %s", e)
            self.client = None

    def generate(self, prompt: str, max_tokens: int = 2000, temperature: float = 0.0) -> str:
        """
        Invoke the Bedrock model and attempt to extract a textual response.
        Supports Anthropic-style models that expect a `messages`-based payload.
        Raises RuntimeError if client not configured.
        """
        if not self.client:
            raise RuntimeError("Bedrock client not configured or boto3 missing")

        try:
            # special-case Anthropic-style models that accept messages payloads
            if "anthropic" in (self.model_id or "").lower():
                # construct messages as shown in your example
                ai_messages = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
                payload = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": int(max_tokens),
                    "temperature": float(temperature),
                    "messages": ai_messages,
                }
                payload_json = json.dumps(payload)
                model_parms = {
                    "modelId": self.model_id,
                    "body": payload_json,
                    "contentType": "application/json"
                }
                resp = self.client.invoke_model(**model_parms)
            else:
                # default generic JSON shape used previously
                payload = {"input": prompt, "temperature": float(temperature), "max_output_tokens": int(max_tokens)}
                resp = self.client.invoke_model(
                    body=json.dumps(payload),
                    modelId=self.model_id,
                    contentType="application/json"
                )

            body = resp.get("body")
            if hasattr(body, "read"):
                raw = body.read()
                try:
                    text = raw.decode("utf-8")
                except Exception:
                    text = raw.decode("latin-1", errors="ignore")
            else:
                text = body if isinstance(body, str) else json.dumps(body)

            # Try to parse JSON and extract common fields
            try:
                j = json.loads(text)
                # look for likely text fields
                if isinstance(j, dict):
                    # Anthropic-style responses may nest under "completion" or "results"
                    for k in ("output","output_text","completion","results","generated_text","content","text"):
                        if k in j:
                            v = j[k]
                            if isinstance(v, str):
                                return v
                            if isinstance(v, list) and v:
                                first = v[0]
                                if isinstance(first, dict):
                                    for kk in ("output_text","generated_text","content","text"):
                                        if kk in first:
                                            return first[kk]
                                if isinstance(first, str):
                                    return first
                # fallback: stringified JSON
                return json.dumps(j)
            except Exception:
                # not JSON, return raw text
                return text
        except Exception as e:
            logger.exception("Bedrock model invocation failed: %s", e)
            raise
