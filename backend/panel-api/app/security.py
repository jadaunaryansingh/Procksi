from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import settings


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# `aud` scopes a token to this service. Until now mentor-api, panel-api and
# student-api all signed with the *same* SECRET_KEY and checked none of this,
# so a token minted by any one service passed verification on the other two —
# one leaked secret compromised three services at once with no boundary
# stopping cross-service replay (audit finding L-1). Each service now has its
# own secret (see .env) and only accepts tokens carrying its own audience.
_AUDIENCE = "panel-api"


def create_access_token(sub: str, extra: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": sub, "exp": expire, "aud": _AUDIENCE, **extra}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm], audience=_AUDIENCE)
    except JWTError:
        return None
