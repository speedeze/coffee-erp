import hashlib
import hmac
import secrets
import json
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.orm import Session
from app.config import SECRET_KEY
from app.database import get_db

# Password Hashing using PBKDF2-HMAC-SHA256
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return f"{salt}:{key.hex()}"

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, key_hex = stored_hash.split(":")
        computed_key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        return hmac.compare_digest(computed_key.hex(), key_hex)
    except Exception:
        return False

# Session token generator using HMAC signature
def create_session_token(user_id: int, username: str, role: str) -> str:
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": (datetime.utcnow() + timedelta(days=7)).isoformat()
    }
    payload_str = json.dumps(payload, separators=(',', ':'))
    signature = hmac.new(SECRET_KEY.encode('utf-8'), payload_str.encode('utf-8'), hashlib.sha256).hexdigest()
    # hex encode payload to make it cookie-safe
    encoded_payload = payload_str.encode('utf-8').hex()
    return f"{encoded_payload}.{signature}"

def verify_session_token(token: str) -> Optional[dict]:
    try:
        encoded_payload, signature = token.split(".")
        payload_str = bytes.fromhex(encoded_payload).decode('utf-8')
        expected_sig = hmac.new(SECRET_KEY.encode('utf-8'), payload_str.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        payload = json.loads(payload_str)
        exp = datetime.fromisoformat(payload["exp"])
        if datetime.utcnow() > exp:
            return None
        return payload
    except Exception:
        return None

# Dependency to get current logged-in user
def get_current_user_optional(request: Request, db: Session = Depends(get_db)):
    # Check session cookie or Authorization Bearer header
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
    
    if not token:
        return None
    
    payload = verify_session_token(token)
    if not payload:
        return None
    
    from app.models.user import User
    user = db.query(User).filter(User.id == payload["user_id"], User.is_active == True).first()
    return user

def get_current_user(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in."
        )
    return user

def require_roles(allowed_roles: List[str]):
    def role_checker(user = Depends(get_current_user)):
        if user.role not in allowed_roles and user.role != "CHIEF_ACCOUNTANT":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires one of the following roles: {', '.join(allowed_roles)}"
            )
        return user
    return role_checker
