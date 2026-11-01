from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.user import User
from app.models.inventory import StockQuant, Item, Warehouse, StockMove
from app.models.manufacturing import RoastingOrder, ProductionOrder
from app.models.sales import SalesInvoice, Customer
from app.models.accounting import JournalEntry
from app.auth import get_current_user_optional, get_current_user

router = APIRouter(tags=["Dashboard"])

@router.get("/")
async def root_redirect(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return RedirectResponse(url="/dashboard", status_code=302)

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="dashboard.html", context={
        "request": request,
        "user": user,
        "active_nav": "dashboard"
    })

@router.get("/api/dashboard/metrics")
async def get_dashboard_metrics(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 1. Total Inventory Valuation
    quants = db.query(StockQuant, Item, Warehouse).join(Item).join(Warehouse).all()
    total_inventory_val = Decimal('0.00')
    raw_beans_kg = Decimal('0.00')
    roasted_coffee_kg = Decimal('0.00')
    finished_goods_units = Decimal('0.00')

    for q, item, wh in quants:
        qty = Decimal(str(q.quantity or 0))
        cost = Decimal(str(item.cost_price or 0))
        val = qty * cost
        total_inventory_val += val

        if wh.code == "WH-RAW":
            raw_beans_kg += qty
        elif wh.code == "WH-ROAST":
            roasted_coffee_kg += qty
        elif wh.code == "WH-FG":
            finished_goods_units += qty

    # 2. Total Receivables Due
    invoices = db.query(SalesInvoice).filter(SalesInvoice.status.in_(["CONFIRMED", "PAID"])).all()
    total_sales = sum([Decimal(str(inv.total_amount)) for inv in invoices])
    total_receivables = sum([
        Decimal(str(inv.total_amount)) - Decimal(str(inv.paid_amount or 0))
        for inv in invoices
    ])

    # 3. Roasting Stats
    total_roasts = db.query(func.count(RoastingOrder.id)).scalar() or 0
    completed_roasts = db.query(func.count(RoastingOrder.id)).filter(RoastingOrder.status == "COMPLETED").scalar() or 0
    recent_roasts = db.query(RoastingOrder).order_by(RoastingOrder.id.desc()).limit(5).all()

    # 4. Recent Journal Entries
    recent_jes = db.query(JournalEntry).order_by(JournalEntry.id.desc()).limit(5).all()

    # 5. Recent Stock Moves
    recent_moves = db.query(StockMove).order_by(StockMove.id.desc()).limit(6).all()

    return {
        "total_inventory_value": round(float(total_inventory_val), 2),
        "raw_beans_kg": round(float(raw_beans_kg), 1),
        "roasted_coffee_kg": round(float(roasted_coffee_kg), 1),
        "finished_goods_units": round(float(finished_goods_units), 0),
        "total_sales": round(float(total_sales), 2),
        "total_receivables": round(float(total_receivables), 2),
        "total_roasts": total_roasts,
        "completed_roasts": completed_roasts,
        "recent_roasts": [r.to_dict() for r in recent_roasts],
        "recent_journals": [j.to_dict() for j in recent_jes],
        "recent_moves": [m.to_dict() for m in recent_moves]
    }
