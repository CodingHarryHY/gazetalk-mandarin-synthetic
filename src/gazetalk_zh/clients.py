from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from .config import DEFAULT_BASE_URL, validate_base_url


class GenerationError(RuntimeError):
    def __init__(self, code: str, *, fatal: bool = False, response: Response | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.fatal = fatal
        self.response = response


@dataclass(frozen=True)
class Response:
    text: str
    response_id: str | None = None
    returned_model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Client(Protocol):
    def generate(self, request: dict[str, Any]) -> Response: ...


class OpenAIClient:
    def __init__(self, timeout: int, base_url: str = DEFAULT_BASE_URL, api_key: str | None = None) -> None:
        base_url = validate_base_url(base_url)
        key = (api_key or "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise GenerationError("missing_api_key", fatal=True)
        from openai import OpenAI

        self._api_key = key
        self.client = OpenAI(api_key=key, base_url=base_url,
                             timeout=timeout, max_retries=0)

    def generate(self, request: dict[str, Any]) -> Response:
        from openai import APIConnectionError, APIStatusError, APITimeoutError

        format_settings = request.get("text", {}).get("format", {})
        request_log = {key: request[key] for key in ("model", "store", "reasoning", "max_output_tokens", "service_tier")
                       if key in request}
        request_log["text_format"] = format_settings
        request_log["input"] = [{"role": item.get("role"), "content_length": len(str(item.get("content", "")))}
                                for item in request.get("input", [])]
        # Print request parameters for API debugging without prompt text or credentials.
        print(json.dumps({"event": "api_request", "parameters": request_log}, ensure_ascii=False),
              file=sys.stderr, flush=True)
        try:
            result = self.client.responses.create(**request)
        except APIStatusError as exc:
            status = exc.status_code
            try:
                body = exc.response.json()
            except ValueError:
                body = None
            error = body.get("error", body) if isinstance(body, dict) else None
            if not isinstance(error, dict):
                error = {"message": error} if error is not None else {}
            details = {}
            for key in ("type", "code", "param", "message"):
                value = error.get(key)
                if value is not None:
                    value = str(value).replace(self._api_key, "[REDACTED]")
                    value = re.sub(r"(?i)\bBearer\s+\S+|\bsk-[A-Za-z0-9_-]+", "[REDACTED]", value)
                    details[key] = value[:1000]
            # Print the HTTP error response with sensitive details redacted.
            print(json.dumps({"event": "api_response", "status_code": status,
                              "request_id": exc.response.headers.get("x-request-id"), "error": details},
                             ensure_ascii=False), file=sys.stderr, flush=True)
            raise GenerationError(f"http_{status}", fatal=status not in (408, 409, 429) and status < 500) from None
        except (APIConnectionError, APITimeoutError):
            # Print a response diagnostic when no HTTP response was received.
            print(json.dumps({"event": "api_response", "error": "connection_or_timeout"}),
                  file=sys.stderr, flush=True)
            raise GenerationError("connection_or_timeout") from None
        usage = result.usage
        # Print the returned response status, model, service tier, and token usage.
        print(json.dumps({"event": "api_response", "status": result.status, "response_id": result.id,
                          "model": result.model, "service_tier": getattr(result, "service_tier", None),
                          "input_tokens": usage.input_tokens if usage else None,
                          "output_tokens": usage.output_tokens if usage else None}),
              file=sys.stderr, flush=True)
        response = Response(result.output_text or "", result.id, result.model,
                            usage.input_tokens if usage else None, usage.output_tokens if usage else None)
        if result.status != "completed":
            reason = getattr(getattr(result, "incomplete_details", None), "reason", None)
            code = "output_token_limit" if reason == "max_output_tokens" else "incomplete_response"
            raise GenerationError(code, response=response)
        for item in result.output:
            for part in getattr(item, "content", []):
                if getattr(part, "type", None) == "refusal":
                    raise GenerationError("model_refusal", response=response)
        if not result.output_text:
            raise GenerationError("empty_response", response=response)
        return response
