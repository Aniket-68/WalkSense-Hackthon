"""MongoDB connection for WalkSense user authentication.

Uses Motor (async MongoDB driver) for non-blocking database operations.

Config via env:
  MONGO_DB_API_KEY                     — Full MongoDB connection string
  MONGODB_DB                           — Database name (default: walksense)
  MONGO_SERVER_SELECTION_TIMEOUT_MS    — server selection timeout (default: 5000)
  MONGO_CONNECT_TIMEOUT_MS             — connect timeout (default: 10000)
  MONGO_SOCKET_TIMEOUT_MS              — socket timeout (default: 20000)
  MONGO_TLS_CA_FILE                    — optional CA bundle file path
  MONGO_TLS_ALLOW_INVALID_CERTS        — allow invalid certs (default: false)
"""

import os
import threading

from loguru import logger
from API.env_loader import bootstrap_environment

bootstrap_environment()

_client = None
_db = None
_client_lock = threading.Lock()


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def get_database():
    """Get or create the async MongoDB database handle."""
    global _client, _db
    if _db is not None:
        return _db

    with _client_lock:
        if _db is not None:
            return _db

        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError:
            logger.warning("[MongoDB] motor not installed. pip install motor")
            return None

        url = os.getenv("MONGO_DB_API_KEY", os.getenv("MONGODB_URL", "mongodb://localhost:27017"))
        db_name = os.getenv("MONGODB_DB", "walksense")

        server_selection_timeout_ms = int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "5000"))
        connect_timeout_ms = int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "10000"))
        socket_timeout_ms = int(os.getenv("MONGO_SOCKET_TIMEOUT_MS", "20000"))
        tls_allow_invalid = _bool_env("MONGO_TLS_ALLOW_INVALID_CERTS", False)
        tls_ca_file = os.getenv("MONGO_TLS_CA_FILE", "").strip()

        client_kwargs = {
            "serverSelectionTimeoutMS": server_selection_timeout_ms,
            "connectTimeoutMS": connect_timeout_ms,
            "socketTimeoutMS": socket_timeout_ms,
            "retryWrites": True,
        }

        # Atlas/SRV connections require TLS. Use certifi by default when available.
        if url.startswith("mongodb+srv://") or ".mongodb.net" in url:
            client_kwargs["tls"] = True

            if tls_ca_file:
                client_kwargs["tlsCAFile"] = tls_ca_file
            else:
                try:
                    import certifi  # type: ignore

                    client_kwargs["tlsCAFile"] = certifi.where()
                except Exception:
                    pass

            if tls_allow_invalid:
                client_kwargs["tlsAllowInvalidCertificates"] = True
                logger.warning("[MongoDB] TLS invalid-certificate mode is enabled")

        try:
            _client = AsyncIOMotorClient(url, **client_kwargs)
            _db = _client[db_name]
            logger.info(f"[MongoDB] Client initialized for database '{db_name}'")
            return _db
        except Exception as exc:
            logger.warning(f"[MongoDB] Client initialization failed: {exc}")
            return None


async def ensure_indexes():
    """Create required indexes on startup."""
    db = get_database()
    if db is None:
        return
    try:
        await db.users.create_index("email", unique=True)
        await db.users.create_index("username", unique=True)
        logger.info("[MongoDB] User indexes ensured (email, username)")
    except Exception as exc:
        logger.warning(f"[MongoDB] Index creation failed: {exc}")


def close_database():
    """Close the MongoDB connection."""
    global _client, _db
    with _client_lock:
        if _client:
            _client.close()
            _client = None
            _db = None
