"""
Auth via Supabase.
- Signup/login proxied through /auth endpoints using Supabase Admin SDK.
- Backend verifies Supabase-issued ES256 JWTs via JWKS.
- User rows are auto-created in SQLite on first verified request.
"""
import logging
from typing import Optional
from functools import lru_cache

import httpx
import jwt as pyjwt
from jwt.algorithms import ECAlgorithm
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from supabase import create_client, Client

from core.config import settings
from core.database import get_db

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer()

_supabase_admin: Optional[Client] = None


def get_supabase_admin() -> Client:
    global _supabase_admin
    if _supabase_admin is None:
        _supabase_admin = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _supabase_admin


@lru_cache(maxsize=1)
def _get_jwks() -> dict:
    """Fetch and cache Supabase JWKS public keys."""
    url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    return {key["kid"]: key for key in resp.json().get("keys", [])}


def _decode_supabase_jwt(token: str) -> Optional[dict]:
    """Verify and decode a Supabase ES256 JWT using JWKS."""
    try:
        header = pyjwt.get_unverified_header(token)
        kid = header.get("kid")
        jwks = _get_jwks()

        if kid not in jwks:
            # Refresh cache once and retry
            _get_jwks.cache_clear()
            jwks = _get_jwks()

        if kid not in jwks:
            logger.warning("Unknown JWT kid: %s", kid)
            return None

        public_key = ECAlgorithm.from_jwk(jwks[kid])
        payload = pyjwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            options={"verify_aud": False},
        )
        return payload
    except pyjwt.ExpiredSignatureError:
        logger.debug("Supabase JWT expired")
        return None
    except Exception as exc:
        logger.debug("JWT decode failed: %s", exc)
        return None


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    from models.user import User

    payload = _decode_supabase_jwt(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    supabase_uid = payload.get("sub")
    if not supabase_uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims")

    # Auto-upsert local user row
    user = db.query(User).filter(User.id == supabase_uid).first()
    if not user:
        email = payload.get("email", "")
        display_name = payload.get("user_metadata", {}).get("display_name", "")
        user = User(id=supabase_uid, email=email, hashed_password="supabase_managed", display_name=display_name)
        db.add(user)
        db.commit()
        db.refresh(user)

    return user
