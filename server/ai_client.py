from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

import httpx


@dataclass
class TextResponse:
    text: str


class GitHubModelsTextClient:
    def __init__(self, token: str, model: str, endpoint: Optional[str] = None):
        self.token = token
        self.model = model
        self.endpoint = endpoint or os.getenv(
            "GITHUB_MODELS_ENDPOINT",
            "https://models.inference.ai.azure.com/chat/completions",
        )
        self.timeout = float(os.getenv("GITHUB_MODELS_TIMEOUT", "20"))

    def generate_content(self, prompt: Any) -> TextResponse:
        if isinstance(prompt, (list, tuple)):
            prompt = "\n".join(str(part) for part in prompt)
        elif prompt is None:
            prompt = ""
        else:
            prompt = str(prompt)

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        model_candidates = [self.model]
        fallback_model = os.getenv("GITHUB_MODELS_FALLBACK_MODEL", "gpt-4.1-mini")
        if fallback_model and fallback_model not in model_candidates:
            model_candidates.append(fallback_model)

        data = None
        last_error: Optional[Exception] = None
        with httpx.Client(timeout=self.timeout) as client:
            for model_name in model_candidates:
                payload = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1")),
                }
                try:
                    response = client.post(self.endpoint, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    self.model = model_name
                    break
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    body = exc.response.text.lower() if exc.response is not None else ""
                    if exc.response is not None and exc.response.status_code == 400 and "unknown model" in body:
                        continue
                    raise
                except Exception as exc:
                    last_error = exc
                    raise

        if data is None:
            if last_error:
                raise last_error
            raise ValueError("GitHub Models returned no response")

        choices = data.get("choices") or []
        if not choices:
            raise ValueError("GitHub Models returned no choices")

        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(str(item))
            content = "".join(parts)

        return TextResponse(text=str(content))


class GroqTextClient:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.endpoint = os.getenv(
            "GROQ_ENDPOINT",
            "https://api.groq.com/openai/v1/chat/completions",
        )
        self.timeout = float(os.getenv("GROQ_TIMEOUT", "20"))

    def generate_content(self, prompt: Any) -> TextResponse:
        if isinstance(prompt, (list, tuple)):
            prompt = "\n".join(str(part) for part in prompt)
        elif prompt is None:
            prompt = ""
        else:
            prompt = str(prompt)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1")),
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(self.endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        choices = data.get("choices") or []
        if not choices:
            raise ValueError("Groq returned no choices")

        message = choices[0].get("message") or {}
        return TextResponse(text=str(message.get("content", "")))


class OpenRouterTextClient:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.endpoint = os.getenv(
            "OPENROUTER_ENDPOINT",
            "https://openrouter.ai/api/v1/chat/completions",
        )
        self.timeout = float(os.getenv("OPENROUTER_TIMEOUT", "25"))
        self.http_referer = os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost:3000")
        self.title = os.getenv("OPENROUTER_APP_TITLE", "TrackEneer")

    def generate_content(self, prompt: Any) -> TextResponse:
        if isinstance(prompt, (list, tuple)):
            prompt = "\n".join(str(part) for part in prompt)
        elif prompt is None:
            prompt = ""
        else:
            prompt = str(prompt)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "HTTP-Referer": self.http_referer,
            "X-OpenRouter-Title": self.title,
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1")),
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(self.endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        choices = data.get("choices") or []
        if not choices:
            raise ValueError("OpenRouter returned no choices")

        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(str(item))
            content = "".join(parts)

        return TextResponse(text=str(content))


class GoogleTextClient:
    def __init__(self, model: Any, fallback_client: Optional[Any] = None):
        self.model = model
        self.fallback_client = fallback_client

    def generate_content(self, prompt: Any) -> Any:
        try:
            return self.model.generate_content(prompt)
        except Exception as exc:
            message = str(exc).lower()
            quota_hit = (
                "429" in message
                or "quota" in message
                or "rate limit" in message
                or "rate-limit" in message
                or "resource_exhausted" in message
            )
            if quota_hit and self.fallback_client is not None:
                return self.fallback_client.generate_content(prompt)
            raise


def _build_groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None

    model_name = os.getenv("GROQ_MODEL") or "llama-3.1-8b-instant"
    return GroqTextClient(api_key, model_name)


def _build_openrouter_client(model_name: Optional[str] = None):
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None

    resolved_model = model_name or os.getenv("OPENROUTER_MODEL") or "openrouter/auto"
    return OpenRouterTextClient(api_key, resolved_model)


def _build_google_client(fallback_client: Optional[Any] = None):
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        import google.generativeai as genai
    except Exception:
        return None

    genai.configure(api_key=api_key)
    model_name = (
        os.getenv("GOOGLE_GENAI_MODEL")
        or os.getenv("GEMINI_MODEL")
        or "gemini-2.0-flash-lite"
    )
    return GoogleTextClient(genai.GenerativeModel(model_name), fallback_client=fallback_client)


def build_text_model(
    provider_override: Optional[str] = None,
    model_override: Optional[str] = None,
):
    provider = (provider_override or os.getenv("LLM_PROVIDER") or "").strip().lower()
    github_token = os.getenv("GITHUB_MODELS_TOKEN") or os.getenv("GITHUB_TOKEN")
    groq_client = _build_groq_client()
    openrouter_client = _build_openrouter_client(model_override)

    if provider == "groq":
        return groq_client or openrouter_client or _build_google_client()

    if provider == "openrouter":
        return openrouter_client or groq_client or _build_google_client()

    if provider in {"google", "gemini"}:
        return _build_google_client(fallback_client=groq_client or openrouter_client) or groq_client or openrouter_client

    use_github = provider in {"github", "github-models", "github_models"}
    if github_token and not provider:
        use_github = True

    if use_github:
        if not github_token:
            return _build_google_client(fallback_client=groq_client or openrouter_client) or groq_client or openrouter_client
        model_name = model_override or os.getenv("GITHUB_MODELS_MODEL") or "gpt-4.1-mini"
        return GitHubModelsTextClient(github_token, model_name)

    if openrouter_client and not provider:
        return openrouter_client

    return _build_google_client(fallback_client=groq_client or openrouter_client) or groq_client or openrouter_client
