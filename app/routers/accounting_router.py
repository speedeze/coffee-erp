from datetime import date
from typing import Optional, List
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models.user import User, AuditLog
from app.models.accounting import Account, JournalEntry, JournalItem
from app.auth import get_current_user_optional, get_current_user
from app.services.accounting_service import (
    create_balanced_journal_entry,
    get_general_ledger,
    get_trial_balance,
    get_income_statement,
    get_trading_account,
    get_balance_sheet
)
from app.services.excel_service import create_excel_streaming_response

router = APIRouter(prefix="/accounting", tags=["Accounting & General Ledger"])

class JournalItemInput(BaseModel):
    account_id: int
    debit: float = 0.0
    credit: float = 0.0
    description: Optional[str] = None

class CreateJournalEntryRequest(BaseModel):
    date: date
    reference: Optional[str] = None
    narration: Optional[str] = None
    items: List[JournalItemInput]

class CreateAccountRequest(BaseModel):
    code: str
    name: str
    name_ar: str
    type: str
    category: str
    parent_id: Optional[int] = None

class UpdateAccountRequest(BaseModel):
    name: str
    name_ar: str
    type: str
    category: str
    parent_id: Optional[int] = None
    is_active: bool = True

# Template Views
@router.get("/coa", response_class=HTMLResponse)
@router.get("/chart-of-accounts", response_class=HTMLResponse)
async def view_coa(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="accounting/coa.html", context={
        "request": request,
        "user": user,
        "active_nav": "accounting",
        "sub_nav": "coa"
    })

@router.get("/journal-entries", response_class=HTMLResponse)
async def view_journal_entries(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="accounting/journal_entries.html", context={
        "request": request,
        "user": user,
        "active_nav": "accounting",
        "sub_nav": "journal_entries"
    })

@router.get("/general-ledger", response_class=HTMLResponse)
async def view_general_ledger(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="accounting/general_ledger.html", context={
        "request": request,
        "user": user,
        "active_nav": "accounting",
        "sub_nav": "general_ledger"
    })

@router.get("/trial-balance", response_class=HTMLResponse)
async def view_trial_balance(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="accounting/trial_balance.html", context={
        "request": request,
        "user": user,
        "active_nav": "accounting",
        "sub_nav": "trial_balance"
    })

@router.get("/trading-account", response_class=HTMLResponse)
async def view_trading_account(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="accounting/trading_account.html", context={
        "request": request,
        "user": user,
        "active_nav": "reports",
        "sub_nav": "trading_account"
    })

@router.get("/profit-loss", response_class=HTMLResponse)
async def view_profit_loss(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="accounting/profit_loss.html", context={
        "request": request,
        "user": user,
        "active_nav": "reports",
        "sub_nav": "profit_loss"
    })

@router.get("/balance-sheet", response_class=HTMLResponse)
async def view_balance_sheet(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="accounting/balance_sheet.html", context={
        "request": request,
        "user": user,
        "active_nav": "reports",
        "sub_nav": "balance_sheet"
    })

# APIs - COA & Accounts
@router.get("/api/accounts")
async def list_accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    accounts = db.query(Account).order_by(Account.code.asc()).all()
    return [a.to_dict() for a in accounts]

@router.post("/api/accounts")
async def create_account(data: CreateAccountRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    existing = db.query(Account).filter(Account.code == data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"رقم الحساب '{data.code}' موجود مسبقاً")

    acc = Account(
        code=data.code,
        name=data.name,
        name_ar=data.name_ar,
        type=data.type,
        category=data.category,
        parent_id=data.parent_id
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc.to_dict()

@router.put("/api/accounts/{id}")
async def update_account(id: int, data: UpdateAccountRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = db.query(Account).filter(Account.id == id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="الحساب غير موجود")
    acc.name = data.name
    acc.name_ar = data.name_ar
    acc.type = data.type
    acc.category = data.category
    acc.parent_id = data.parent_id
    acc.is_active = data.is_active
    db.commit()
    db.refresh(acc)
    return acc.to_dict()

@router.delete("/api/accounts/{id}")
async def delete_account(id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = db.query(Account).filter(Account.id == id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="الحساب غير موجود")
    has_items = db.query(JournalItem).filter(JournalItem.account_id == id).first()
    if has_items:
        acc.is_active = False
        db.commit()
        return {"success": True, "message": "تم تعطيل الحساب لوجود حركات وقيود سابقة مسجلة عليه"}
    db.delete(acc)
    db.commit()
    return {"success": True, "message": "تم حذف الحساب بنجاح"}

@router.get("/api/coa/export")
async def export_coa_excel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    accounts = db.query(Account).order_by(Account.code.asc()).all()
    headers = ["رقم الحساب", "اسم الحساب بالعربية", "اسم الحساب بالإنجليزية", "النوع", "التصنيف", "الحالة"]
    rows = []
    type_map = {"ASSET": "أصول", "LIABILITY": "خصوم والتزامات", "EQUITY": "حقوق ملكية", "REVENUE": "إيرادات", "EXPENSE": "مصروفات"}
    for a in accounts:
        rows.append([
            a.code,
            a.name_ar,
            a.name,
            type_map.get(a.type, a.type),
            a.category,
            "نشط" if a.is_active else "معطل"
        ])
    return create_excel_streaming_response("دليل_الحسابات_الشامل", "دليل الحسابات", headers, rows, "شجرة ودليل الحسابات المحاسبية - CoffeeRoast ERP")

# APIs - Journal Entries
@router.get("/api/journal-entries")
async def list_journal_entries(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    entries = db.query(JournalEntry).order_by(JournalEntry.id.desc()).all()
    return [e.to_dict() for e in entries]

@router.post("/api/journal-entries")
async def create_journal_entry(data: CreateJournalEntryRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        lines = [item.dict() for item in data.items]
        entry = create_balanced_journal_entry(
            db=db,
            entry_date=data.date,
            reference=data.reference or "يدوي",
            source_document="MANUAL",
            source_id=None,
            narration=data.narration or "قيد يومية يدوي",
            lines=lines,
            created_by_id=user.id
        )
        db.commit()
        db.refresh(entry)
        return entry.to_dict()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/api/journal-entries/export")
async def export_journal_entries_excel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    entries = db.query(JournalEntry).order_by(JournalEntry.id.desc()).all()
    headers = ["رقم القيد", "التاريخ", "المرجع", "المصدر", "الحالة", "إجمالي المدين", "إجمالي الدائن", "البيان"]
    rows = []
    for e in entries:
        rows.append([
            e.entry_number,
            e.date.strftime("%Y-%m-%d"),
            e.reference or "-",
            e.source_document or "-",
            "مرحل" if e.status == "POSTED" else e.status,
            float(e.total_debit or 0),
            float(e.total_credit or 0),
            e.narration or "-"
        ])
    return create_excel_streaming_response("دفتر_قيود_اليومية", "قيود اليومية", headers, rows, "سجل قيود اليومية المحاسبية المزدوجة")

# APIs - General Ledger
@router.get("/api/general-ledger")
async def api_general_ledger(
    account_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        return get_general_ledger(db, account_id, start_date, end_date)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# APIs - Financial Statements
@router.get("/api/trial-balance")
async def api_trial_balance(
    as_of_date: Optional[date] = None,
    include_zero_balances: bool = Query(True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_trial_balance(db, as_of_date, include_zero_balances)

@router.get("/api/trial-balance/export")
async def export_trial_balance_excel(
    as_of_date: Optional[date] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tb = get_trial_balance(db, as_of_date, include_zero_balances=True)
    headers = [
        "رقم الحساب", "اسم الحساب بالعربية", "اسم الحساب بالإنجليزية", "المستوى",
        "حركات مدينة", "حركات دائنة", "رصيد مدين ختامي", "رصيد دائن ختامي"
    ]
    rows = []
    for r in tb["rows"]:
        rows.append([
            r["code"],
            ("  " * (r["level"] - 1)) + r["name_ar"] + (" (رئيسي)" if r["is_parent"] else ""),
            r["name"],
            f"المستوى {r['level']}",
            r["total_debit"],
            r["total_credit"],
            r["net_debit"] if r["net_debit"] > 0 else 0.0,
            r["net_credit"] if r["net_credit"] > 0 else 0.0
        ])
    # Add grand total row
    rows.append([
        "الإجمالي الكلي للميزان",
        "متزن" if tb["is_balanced"] else "غير متزن",
        "-",
        "-",
        tb["movement_debit"],
        tb["movement_credit"],
        tb["total_debit"],
        tb["total_credit"]
    ])
    date_str = as_of_date.strftime("%Y-%m-%d") if as_of_date else date.today().strftime("%Y-%m-%d")
    return create_excel_streaming_response(f"ميزان_المراجعة_{date_str}", "ميزان المراجعة", headers, rows, f"ميزان المراجعة بالأرصدة والمجاميع حتى {date_str} - CoffeeRoast ERP")

@router.get("/api/trading-account")
async def api_trading_account(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_trading_account(db, start_date, end_date)

@router.get("/api/profit-loss")
async def api_profit_loss(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_income_statement(db, start_date, end_date)

@router.get("/api/balance-sheet")
async def api_balance_sheet(
    as_of_date: Optional[date] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_balance_sheet(db, as_of_date)
