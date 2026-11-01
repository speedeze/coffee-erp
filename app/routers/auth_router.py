from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models.user import User, AuditLog
from app.auth import verify_password, create_session_token, get_current_user_optional, get_current_user

router = APIRouter(tags=["Authentication"])

class LoginRequest(BaseModel):
    username: str
    password: str

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    # If already logged in, redirect to dashboard
    user = get_current_user_optional(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    
    # Return login page HTML template
    from app.main import templates
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request})

@router.post("/api/auth/login")
async def api_login(data: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )

    token = create_session_token(user.id, user.username, user.role)
    
    # Set HTTP-only session cookie
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=7 * 24 * 3600,
        samesite="lax"
    )

    # Log audit entry
    audit = AuditLog(
        user_id=user.id,
        action="LOGIN",
        entity_type="User",
        entity_id=user.id,
        details=f"Accountant logged in: {user.role}",
        ip_address=request.client.host if request.client else None
    )
    db.add(audit)
    db.commit()

    return {
        "success": True,
        "token": token,
        "user": user.to_dict()
    }

@router.post("/api/auth/logout")
async def api_logout(response: Response, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if user:
        audit = AuditLog(
            user_id=user.id,
            action="LOGOUT",
            entity_type="User",
            entity_id=user.id,
            details="Accountant logged out",
            ip_address=request.client.host if request.client else None
        )
        db.add(audit)
        db.commit()

    response.delete_cookie(key="session_token")
    return {"success": True, "message": "Logged out successfully"}

@router.get("/api/auth/me")
async def api_me(user: User = Depends(get_current_user)):
    return user.to_dict()
