from datetime import date
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models.user import User, AuditLog
from app.models.treasury import TreasuryAccount, ReceiptVoucher, PaymentVoucher
from app.auth import get_current_user_optional, get_current_user
from app.services.treasury_service import process_receipt_voucher, process_payment_voucher
from app.services.excel_service import create_excel_streaming_response

router = APIRouter(prefix="/treasury", tags=["Treasury & Bank Accounts"])

class CreateTreasuryAccountRequest(BaseModel):
    code: str
    name: str
    name_ar: str
    account_type: str = "CASH"
    currency: str = "USD"
    gl_account_id: int

class UpdateTreasuryAccountRequest(BaseModel):
    name: str
    name_ar: str
    account_type: str = "CASH"
    is_active: bool = True

class CreateReceiptRequest(BaseModel):
    date: date
    treasury_account_id: int
    amount: float
    credit_account_id: int
    customer_id: Optional[int] = None
    invoice_id: Optional[int] = None
    description: Optional[str] = None
    payer_name: Optional[str] = None

class CreatePaymentRequest(BaseModel):
    date: date
    treasury_account_id: int
    amount: float
    debit_account_id: int
    supplier_id: Optional[int] = None
    purchase_order_id: Optional[int] = None
    description: Optional[str] = None
    beneficiary_name: Optional[str] = None

# Views
@router.get("/accounts", response_class=HTMLResponse)
async def view_treasury_accounts(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="treasury/accounts.html", context={
        "request": request,
        "user": user,
        "active_nav": "treasury",
        "sub_nav": "accounts"
    })

@router.get("/receipts", response_class=HTMLResponse)
async def view_receipts(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="treasury/receipts.html", context={
        "request": request,
        "user": user,
        "active_nav": "treasury",
        "sub_nav": "receipts"
    })

@router.get("/payments", response_class=HTMLResponse)
async def view_payments(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="treasury/payments.html", context={
        "request": request,
        "user": user,
        "active_nav": "treasury",
        "sub_nav": "payments"
    })

# APIs - Accounts
@router.get("/api/accounts")
async def list_treasury_accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    accounts = db.query(TreasuryAccount).filter(TreasuryAccount.is_active == True).all()
    return [a.to_dict() for a in accounts]

@router.post("/api/accounts")
async def create_treasury_account(data: CreateTreasuryAccountRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    existing = db.query(TreasuryAccount).filter(TreasuryAccount.code == data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"كود الحساب '{data.code}' موجود مسبقاً")

    acc = TreasuryAccount(
        code=data.code,
        name=data.name,
        name_ar=data.name_ar,
        account_type=data.account_type,
        currency=data.currency,
        gl_account_id=data.gl_account_id
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc.to_dict()

@router.put("/api/accounts/{id}")
async def update_treasury_account(id: int, data: UpdateTreasuryAccountRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = db.query(TreasuryAccount).filter(TreasuryAccount.id == id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="حساب الخزينة غير موجود")
    acc.name = data.name
    acc.name_ar = data.name_ar
    acc.account_type = data.account_type
    acc.is_active = data.is_active
    db.commit()
    db.refresh(acc)
    return acc.to_dict()

# APIs - Receipts
@router.get("/api/receipts")
async def list_receipts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    receipts = db.query(ReceiptVoucher).order_by(ReceiptVoucher.id.desc()).all()
    return [r.to_dict() for r in receipts]

@router.post("/api/receipts")
async def create_receipt(data: CreateReceiptRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        voucher = process_receipt_voucher(
            db=db,
            voucher_date=data.date,
            treasury_account_id=data.treasury_account_id,
            amount=Decimal(str(data.amount)),
            credit_account_id=data.credit_account_id,
            customer_id=data.customer_id,
            invoice_id=data.invoice_id,
            description=data.description,
            payer_name=data.payer_name,
            user_id=user.id
        )
        return voucher.to_dict()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/api/receipts/{id}")
async def delete_receipt(id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    voucher = db.query(ReceiptVoucher).filter(ReceiptVoucher.id == id).first()
    if not voucher:
        raise HTTPException(status_code=404, detail="سند القبض غير موجود")
    if voucher.status != "DRAFT":
        raise HTTPException(status_code=400, detail="لا يمكن حذف سند قبض تم ترحيله")
    db.delete(voucher)
    db.commit()
    return {"success": True, "message": "تم حذف السند بنجاح"}

@router.get("/api/receipts/export")
async def export_receipts_excel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    receipts = db.query(ReceiptVoucher).order_by(ReceiptVoucher.id.desc()).all()
    headers = ["رقم السند", "التاريخ", "الخزينة/البنك", "المبلغ", "الدافع/العميل", "البيان", "رقم القيد الآلي"]
    rows = []
    for r in receipts:
        rows.append([
            r.voucher_number,
            r.date.strftime("%Y-%m-%d"),
            r.treasury_account.name_ar if r.treasury_account else "-",
            float(r.amount or 0),
            r.payer_name or (r.customer.name_ar if r.customer else "-"),
            r.description or "-",
            f"#{r.journal_entry_id}" if r.journal_entry_id else "-"
        ])
    return create_excel_streaming_response("سندات_القبض_النقدية_والبنكية", "سندات القبض", headers, rows, "سجل المقبوضات النقدية والبنكية")

# APIs - Payments
@router.get("/api/payments")
async def list_payments(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payments = db.query(PaymentVoucher).order_by(PaymentVoucher.id.desc()).all()
    return [p.to_dict() for p in payments]

@router.post("/api/payments")
async def create_payment(data: CreatePaymentRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        voucher = process_payment_voucher(
            db=db,
            voucher_date=data.date,
            treasury_account_id=data.treasury_account_id,
            amount=Decimal(str(data.amount)),
            debit_account_id=data.debit_account_id,
            supplier_id=data.supplier_id,
            purchase_order_id=data.purchase_order_id,
            description=data.description,
            beneficiary_name=data.beneficiary_name,
            user_id=user.id
        )
        return voucher.to_dict()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/api/payments/{id}")
async def delete_payment(id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    voucher = db.query(PaymentVoucher).filter(PaymentVoucher.id == id).first()
    if not voucher:
        raise HTTPException(status_code=404, detail="سند الصرف غير موجود")
    if voucher.status != "DRAFT":
        raise HTTPException(status_code=400, detail="لا يمكن حذف سند صرف تم ترحيله")
    db.delete(voucher)
    db.commit()
    return {"success": True, "message": "تم حذف السند بنجاح"}

@router.get("/api/payments/export")
async def export_payments_excel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payments = db.query(PaymentVoucher).order_by(PaymentVoucher.id.desc()).all()
    headers = ["رقم السند", "التاريخ", "الخزينة/البنك", "المبلغ", "المستفيد/المورد", "البيان", "رقم القيد الآلي"]
    rows = []
    for p in payments:
        rows.append([
            p.voucher_number,
            p.date.strftime("%Y-%m-%d"),
            p.treasury_account.name_ar if p.treasury_account else "-",
            float(p.amount or 0),
            p.beneficiary_name or (p.supplier.name_ar if p.supplier else "-"),
            p.description or "-",
            f"#{p.journal_entry_id}" if p.journal_entry_id else "-"
        ])
    return create_excel_streaming_response("سندات_الصرف_والمدفوعات", "سندات الصرف", headers, rows, "سجل المدفوعات وسندات الصرف النقدية والبنكية")
