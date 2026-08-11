import argparse
import json
import os
import sys
from typing import Any

import requests


BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_SAVE_PATH = "openrouter_models.json"


def get_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }


def fetch_json(url: str, api_key: str) -> Any:
    response = requests.get(url, headers=get_headers(api_key), timeout=30)
    response.raise_for_status()
    return response.json()


def as_bool_label(value: Any) -> str:
    return "yes" if bool(value) else "no"


def print_key_info(key_data: dict[str, Any]) -> None:
    print("OpenRouter key info")
    print(f"  label:        {key_data.get('label', 'unknown')}")
    print(f"  free tier:    {as_bool_label(key_data.get('is_free_tier'))}")
    print(f"  management:   {as_bool_label(key_data.get('is_management_key'))}")
    print(f"  provisioning: {as_bool_label(key_data.get('is_provisioning_key'))}")
    print(f"  expires_at:   {key_data.get('expires_at', 'unknown')}")
    print(f"  usage_monthly:{key_data.get('usage_monthly', 0)}")
    print()


def print_models(models: list[dict[str, Any]]) -> None:
    print(f"Authenticated model count: {len(models)}")
    print()
    for idx, model in enumerate(models, start=1):
        model_id = model.get("id", "")
        name = model.get("name", "")
        context = model.get("context_length", "")
        modality = (model.get("architecture") or {}).get("modality", "")
        pricing = model.get("pricing") or {}
        prompt_cost = pricing.get("prompt", "")
        completion_cost = pricing.get("completion", "")
        print(
            f"{idx:03d}. {model_id}\n"
            f"     name: {name}\n"
            f"     modality: {modality or 'unknown'}\n"
            f"     context_length: {context}\n"
            f"     prompt_cost: {prompt_cost} | completion_cost: {completion_cost}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List OpenRouter models available to an authenticated API key."
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OPENROUTER_API_KEY"),
        help="OpenRouter API key. Defaults to OPENROUTER_API_KEY.",
    )
    parser.add_argument(
        "--save",
        nargs="?",
        const=DEFAULT_SAVE_PATH,
        help=f"Save the raw /models payload to JSON. Default path: {DEFAULT_SAVE_PATH}",
    )
    args = parser.parse_args()

    if not args.api_key:
        print("Missing API key. Pass --api-key or set OPENROUTER_API_KEY.", file=sys.stderr)
        return 1

    try:
        key_payload = fetch_json(f"{BASE_URL}/auth/key", args.api_key)
        models_payload = fetch_json(f"{BASE_URL}/models", args.api_key)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        body = exc.response.text[:1000] if exc.response is not None else str(exc)
        print(f"OpenRouter request failed ({status}): {body}", file=sys.stderr)
        return 2
    except requests.RequestException as exc:
        print(f"Network error while calling OpenRouter: {exc}", file=sys.stderr)
        return 3

    key_data = key_payload.get("data") or {}
    models = models_payload.get("data") or []

    print_key_info(key_data)
    print_models(models)

    if args.save:
        with open(args.save, "w", encoding="utf-8") as fh:
            json.dump(models_payload, fh, indent=2, ensure_ascii=False)
        print()
        print(f"Saved raw model payload to {args.save}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
