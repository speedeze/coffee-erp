from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models.user import User, AuditLog
from app.auth import get_current_user_optional, get_current_user, require_roles, hash_password
from app.services.excel_service import create_excel_streaming_response

router = APIRouter(prefix="/users", tags=["Users & Audit Trail"])

class CreateUserRequest(BaseModel):
    username: str
    full_name: str
    full_name_ar: str
    email: str
    password: str
    role: str

class UpdateUserRoleRequest(BaseModel):
    user_id: int
    role: str
    is_active: bool

# Views
@router.get("", response_class=HTMLResponse)
@router.get("/list", response_class=HTMLResponse)
async def view_users(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="users/list.html", context={
        "request": request,
        "user": user,
        "active_nav": "settings",
        "sub_nav": "users_list"
    })

@router.get("/audit-trail", response_class=HTMLResponse)
async def view_audit_trail(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="users/audit_trail.html", context={
        "request": request,
        "user": user,
        "active_nav": "settings",
        "sub_nav": "audit_trail"
    })

# APIs
@router.get("/api/list")
async def list_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [u.to_dict() for u in users]

@router.post("/api/create")
async def create_user(
    data: CreateUserRequest,
    user: User = Depends(require_roles(["CHIEF_ACCOUNTANT"])),
    db: Session = Depends(get_db)
):
    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="اسم المستخدم موجود مسبقاً")

    new_user = User(
        username=data.username,
        full_name=data.full_name,
        full_name_ar=data.full_name_ar,
        email=data.email,
        hashed_password=hash_password(data.password),
        role=data.role,
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user.to_dict()

@router.post("/api/update")
async def update_user(
    data: UpdateUserRoleRequest,
    user: User = Depends(require_roles(["CHIEF_ACCOUNTANT"])),
    db: Session = Depends(get_db)
):
    target_user = db.query(User).filter(User.id == data.user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    
    target_user.role = data.role
    target_user.is_active = data.is_active
    db.commit()
    return target_user.to_dict()

@router.delete("/api/{id}")
async def delete_user(
    id: int,
    user: User = Depends(require_roles(["CHIEF_ACCOUNTANT"])),
    db: Session = Depends(get_db)
):
    if user.id == id:
        raise HTTPException(status_code=400, detail="لا يمكنك حذف حسابك الحالي")
    target_user = db.query(User).filter(User.id == id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    target_user.is_active = False
    db.commit()
    return {"success": True, "message": "تم تعطيل المستخدم بنجاح"}

@router.get("/api/audit-trail")
async def get_audit_trail(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(200).all()
    return [l.to_dict() for l in logs]

@router.get("/api/audit-trail/export")
async def export_audit_trail_excel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(1000).all()
    headers = ["رقم الحركة", "التاريخ والوقت", "المستخدم", "نوع العملية", "الكيان", "التفاصيل"]
    rows = []
    for l in logs:
        rows.append([
            l.id,
            l.timestamp.strftime("%Y-%m-%d %H:%M:%S") if l.timestamp else "-",
            l.user.full_name_ar if l.user else "-",
            l.action,
            l.entity_type,
            l.details
        ])
    return create_excel_streaming_response("سجل_الرقابة_وتتبع_العمليات", "سجل الرقابة", headers, rows, "سجل الرقابة وتتبع الحركات المحاسبية - CoffeeRoast ERP")
