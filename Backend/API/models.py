"""User model and database operations for WalkSense (MongoDB).

User document schema:
  {
    "_id":           ObjectId,
    "email":         str (unique),
    "username":      str (unique),
    "password_hash": str (bcrypt),
    "created_at":    float (epoch)
  }
"""

import time
from typing import Optional, Dict, Any

import bcrypt
from loguru import logger
from pydantic import BaseModel, EmailStr, field_validator


# ── Request / Response Schemas ─────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    confirm_password: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("username")
    @classmethod
    def username_min_length(cls, v):
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    created_at: float


# ── Password hashing ─────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ── Database Operations ──────────────────────

async def create_user(email: str, username: str, password: str) -> Optional[Dict[str, Any]]:
    """Create a new user. Returns user dict or None if email/username already exists."""
    from API.database import get_database

    db = get_database()
    if db is None:
        raise RuntimeError("Database not available")

    # Check duplicates
    try:
        existing = await db.users.find_one({"$or": [{"email": email}, {"username": username}]})
    except Exception as exc:
        raise RuntimeError(f"Database lookup failed: {exc}") from exc

    if existing:
        if existing.get("email") == email:
            return None  # Email taken
        raise ValueError("Username already taken")

    user_doc = {
        "email": email,
        "username": username,
        "password_hash": hash_password(password),
        "created_at": time.time(),
    }

    try:
        result = await db.users.insert_one(user_doc)
    except Exception as exc:
        raise RuntimeError(f"Database write failed: {exc}") from exc

    user_doc["_id"] = result.inserted_id
    logger.info(f"[Auth] User created: {email} ({username})")
    return user_doc


async def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate by email + password. Returns user dict or None."""
    from API.database import get_database

    db = get_database()
    if db is None:
        raise RuntimeError("Database not available")

    try:
        user = await db.users.find_one({"email": email})
    except Exception as exc:
        raise RuntimeError(f"Database lookup failed: {exc}") from exc

    if not user:
        return None

    if not verify_password(password, user["password_hash"]):
        return None

    return user


async def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Fetch user by MongoDB ObjectId string."""
    from bson import ObjectId
    from API.database import get_database

    db = get_database()
    if db is None:
        return None

    try:
        return await db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None
