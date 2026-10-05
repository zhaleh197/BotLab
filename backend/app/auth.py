from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import JWT_DAYS, JWT_SECRET
from .db import SessionLocal, User

_bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def check_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


def make_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=JWT_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": exp}, JWT_SECRET, algorithm="HS256")


def current_user(cred: HTTPAuthorizationCredentials = Depends(_bearer)) -> User:
    if not cred:
        raise HTTPException(401, "ابتدا وارد شوید")
    try:
        uid = int(jwt.decode(cred.credentials, JWT_SECRET, algorithms=["HS256"])["sub"])
    except Exception:
        raise HTTPException(401, "نشست شما منقضی شده است؛ دوباره وارد شوید")
    with SessionLocal() as db:
        user = db.get(User, uid)
    if not user:
        raise HTTPException(401, "کاربر یافت نشد")
    return user
