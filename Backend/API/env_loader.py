"""Environment/bootstrap helpers for runtime secrets.

Policy:
- development/test: load local environment + .env values.
- staging/production: fetch secret values from AWS Secrets Manager.
"""

from __future__ import annotations

import base64
import json
import os
import threading
from typing import Dict, Iterable, Tuple

from dotenv import load_dotenv
from loguru import logger

_BOOTSTRAP_LOCK = threading.Lock()
_BOOTSTRAPPED = False
_AWS_SECRET_ENVS = {"staging", "production"}


def _runtime_env() -> str:
    return (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "development").strip().lower()


def _parse_secret_map(secret_payload: str, secret_name: str) -> Dict[str, str]:
    try:
        parsed = json.loads(secret_payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"AWS secret '{secret_name}' must be valid JSON object of env keys/values."
        ) from exc

    if not isinstance(parsed, dict):
        raise RuntimeError(f"AWS secret '{secret_name}' must decode to a JSON object.")

    env_map: Dict[str, str] = {}
    for key, value in parsed.items():
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            env_map[str(key)] = json.dumps(value)
        else:
            env_map[str(key)] = str(value)
    return env_map


def _aws_client():
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "AWS secret loading requires boto3/botocore. Install backend requirements."
        ) from exc

    session = boto3.session.Session()
    region_name = (
        os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or "ap-southeast-1"
    ).strip()
    return session.client(service_name="secretsmanager", region_name=region_name), region_name


def _read_secret_string(client, secret_name: str, region_name: str) -> str:
    try:
        from botocore.exceptions import ClientError
    except ImportError as exc:
        raise RuntimeError(
            "AWS secret loading requires boto3/botocore. Install backend requirements."
        ) from exc

    try:
        response = client.get_secret_value(SecretId=secret_name)
    except ClientError as exc:
        raise RuntimeError(
            f"Failed to load AWS secret '{secret_name}' in region '{region_name}'."
        ) from exc

    secret_string = response.get("SecretString")
    if not secret_string:
        secret_binary = response.get("SecretBinary")
        if secret_binary:
            secret_string = base64.b64decode(secret_binary).decode("utf-8")

    if not secret_string:
        raise RuntimeError(f"AWS secret '{secret_name}' did not contain SecretString/SecretBinary.")

    return secret_string


def _fetch_aws_secret_map(secret_name: str) -> Dict[str, str]:
    client, region_name = _aws_client()
    secret_string = _read_secret_string(client, secret_name, region_name)
    return _parse_secret_map(secret_string, secret_name)


def _csv_secret_keys(raw: str) -> Tuple[str, ...]:
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _extract_single_secret_value(secret_id: str, payload: str) -> str:
    """
    Accept either raw plaintext secret values or tiny JSON wrappers.
    Supported JSON forms:
      {"<secret_id>": "..."} or {"value": "..."} or {"secret": "..."}
    """
    payload = payload.strip()
    if not payload:
        return payload

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return payload

    if isinstance(parsed, str):
        return parsed
    if isinstance(parsed, dict):
        for candidate in (secret_id, "value", "secret"):
            value = parsed.get(candidate)
            if isinstance(value, str):
                return value
    return payload


def _fetch_individual_aws_secrets(secret_ids: Iterable[str]) -> Dict[str, str]:
    client, region_name = _aws_client()
    loaded: Dict[str, str] = {}
    for secret_id in secret_ids:
        secret_string = _read_secret_string(client, secret_id, region_name)
        loaded[secret_id] = _extract_single_secret_value(secret_id, secret_string)
    return loaded


def bootstrap_environment() -> None:
    """Load environment values exactly once per process."""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    with _BOOTSTRAP_LOCK:
        if _BOOTSTRAPPED:
            return

        # Never overwrite explicitly-provided env vars.
        load_dotenv(override=False)

        runtime_env = _runtime_env()
        if runtime_env not in _AWS_SECRET_ENVS:
            logger.info(f"[SECRETS] APP_ENV={runtime_env} -> using local environment/.env")
            _BOOTSTRAPPED = True
            return

        # Preferred mode: one AWS secret per env key.
        # Fallback mode: a single JSON secret object (AWS_SECRET_NAME).
        secret_keys = _csv_secret_keys(
            os.getenv(
                "AWS_SECRET_KEYS",
                "GEMINI_API_KEY,DEEPGRAM_API_KEY,CARTESIA_API_KEY,MONGO_DB_API_KEY",
            )
        )
        secret_name = os.getenv("AWS_SECRET_NAME", "walksense-hackathon-prototype").strip()

        if secret_keys:
            missing_keys = tuple(key for key in secret_keys if not os.getenv(key))
            if missing_keys:
                secret_map = _fetch_individual_aws_secrets(missing_keys)
                source_desc = f"individual secrets ({','.join(missing_keys)})"
            else:
                secret_map = {}
                source_desc = "preloaded runtime environment"
        else:
            secret_map = _fetch_aws_secret_map(secret_name)
            source_desc = f"secret '{secret_name}'"

        for key, value in secret_map.items():
            os.environ[key] = value

        if secret_map:
            logger.info(
                f"[SECRETS] APP_ENV={runtime_env} -> loaded {len(secret_map)} keys from AWS {source_desc}"
            )
        else:
            logger.info(
                f"[SECRETS] APP_ENV={runtime_env} -> using {source_desc}; no AWS fetch needed"
            )
        _BOOTSTRAPPED = True
