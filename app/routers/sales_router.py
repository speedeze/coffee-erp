from datetime import date
from decimal import Decimal
from typing import Optional, List
from fastapi import APIRouter, Depends, Request, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from app.database import get_db
from app.models.user import User, AuditLog
from app.models.sales import Customer, SalesInvoice, SalesInvoiceItem
from app.models.inventory import Warehouse
from app.auth import get_current_user_optional, get_current_user
from app.services.sales_service import confirm_sales_invoice, get_customer_aging_report
from app.services.excel_service import (
    create_excel_streaming_response,
    create_csv_streaming_response,
    generate_customers_template,
    import_customers_from_bytes
)

router = APIRouter(prefix="/sales", tags=["Wholesale Sales & Invoicing"])

class CreateCustomerRequest(BaseModel):
    code: str
    name: str
    name_ar: str
    customer_type: str = "CAFE"
    phone: Optional[str] = None
    email: Optional[str] = None
    tax_number: Optional[str] = None
    credit_limit: float = 0.0
    credit_period_days: int = 30

class UpdateCustomerRequest(BaseModel):
    name: str
    name_ar: str
    customer_type: str = "CAFE"
    phone: Optional[str] = None
    email: Optional[str] = None
    tax_number: Optional[str] = None
    credit_limit: float = 0.0
    credit_period_days: int = 30
    is_active: bool = True

class InvoiceItemInput(BaseModel):
    item_id: int
    quantity: float
    uom_id: int
    unit_price: float

class CreateInvoiceRequest(BaseModel):
    date: date
    due_date: Optional[date] = None
    customer_id: int
    payment_terms: str = "NET30"
    tax_rate: float = 0.0
    discount_amount: float = 0.0
    warehouse_id: Optional[int] = None
    notes: Optional[str] = None
    items: List[InvoiceItemInput]

# Template Views
@router.get("/customers", response_class=HTMLResponse)
async def view_customers(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="sales/customers.html", context={
        "request": request,
        "user": user,
        "active_nav": "sales",
        "sub_nav": "customers"
    })

@router.get("/invoices", response_class=HTMLResponse)
async def view_invoices(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="sales/invoices.html", context={
        "request": request,
        "user": user,
        "active_nav": "sales",
        "sub_nav": "invoices"
    })

@router.get("/aging", response_class=HTMLResponse)
async def view_aging(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="sales/aging.html", context={
        "request": request,
        "user": user,
        "active_nav": "sales",
        "sub_nav": "aging"
    })

# Customer APIs
@router.get("/api/customers")
async def list_customers(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    customers = db.query(Customer).filter(Customer.is_active == True).order_by(Customer.id.desc()).all()
    return [c.to_dict() for c in customers]

@router.post("/api/customers")
async def create_customer(data: CreateCustomerRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    existing = db.query(Customer).filter(Customer.code == data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"كود العميل '{data.code}' مسجل مسبقاً")

    customer = Customer(
        code=data.code,
        name=data.name,
        name_ar=data.name_ar,
        customer_type=data.customer_type,
        phone=data.phone,
        email=data.email,
        tax_number=data.tax_number,
        credit_limit=Decimal(str(data.credit_limit)),
        credit_period_days=data.credit_period_days
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer.to_dict()

@router.put("/api/customers/{id}")
async def update_customer(id: int, data: UpdateCustomerRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="العميل غير موجود")

    customer.name = data.name
    customer.name_ar = data.name_ar
    customer.customer_type = data.customer_type
    customer.phone = data.phone
    customer.email = data.email
    customer.tax_number = data.tax_number
    customer.credit_limit = Decimal(str(data.credit_limit))
    customer.credit_period_days = data.credit_period_days
    customer.is_active = data.is_active
    db.commit()
    db.refresh(customer)
    return customer.to_dict()

@router.delete("/api/customers/{id}")
async def delete_customer(id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="العميل غير موجود")

    # Check if invoices exist
    has_invs = db.query(SalesInvoice).filter(SalesInvoice.customer_id == id).first()
    if has_invs:
        # Soft delete
        customer.is_active = False
        db.commit()
        return {"success": True, "message": "تم تعطيل العميل بنجاح لوجود فواتير مرتبطة به"}

    db.delete(customer)
    db.commit()
    return {"success": True, "message": "تم حذف العميل بنجاح"}

# Customer Excel Export & Import
@router.get("/api/customers/export")
async def export_customers_excel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    customers = db.query(Customer).all()
    headers = [
        "كود العميل", "الاسم بالعربية", "الاسم بالإنجليزية", "نوع العميل",
        "الهاتف", "البريد الإلكتروني", "الرقم الضريبي", "الحد الائتماني", "فترة الائتمان (أيام)", "الحالة"
    ]
    rows = []
    for c in customers:
        rows.append([
            c.code,
            c.name_ar,
            c.name,
            c.customer_type,
            c.phone or "-",
            c.email or "-",
            c.tax_number or "-",
            float(c.credit_limit or 0),
            c.credit_period_days,
            "نشط" if c.is_active else "معطل"
        ])
    return create_excel_streaming_response("دليل_العملاء", "العملاء", headers, rows, "سجل عملاء ومقاهي الجملة - CoffeeRoast ERP")

@router.get("/api/customers/template")
async def get_customers_template(user: User = Depends(get_current_user)):
    return generate_customers_template()

@router.post("/api/customers/import")
async def import_customers(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    content = await file.read()
    try:
        result = import_customers_from_bytes(content, file.filename, db, user.id)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"خطأ أثناء معالجة الملف: {str(e)}")

# Invoices APIs
@router.get("/api/invoices")
async def list_invoices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    invoices = db.query(SalesInvoice).order_by(SalesInvoice.id.desc()).all()
    return [inv.to_dict() for inv in invoices]

@router.get("/api/invoices/{id}")
async def get_invoice(id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inv = db.query(SalesInvoice).filter(SalesInvoice.id == id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="الفاتورة غير موجودة")
    return inv.to_dict()

@router.post("/api/invoices")
async def create_sales_invoice(data: CreateInvoiceRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="العميل غير موجود")

    fg_wh_id = data.warehouse_id
    if not fg_wh_id:
        wh = db.query(Warehouse).filter(Warehouse.code == "WH-FG").first()
        fg_wh_id = wh.id

    count = db.query(func.count(SalesInvoice.id)).scalar() or 0
    inv_num = f"INV-{date.today().year}-{(count + 1):04d}"

    subtotal = Decimal('0.00')
    line_objs = []
    for item_in in data.items:
        qty = Decimal(str(item_in.quantity))
        price = Decimal(str(item_in.unit_price))
        line_total = (qty * price).quantize(Decimal('0.01'))
        subtotal += line_total

        line_objs.append(SalesInvoiceItem(
            item_id=item_in.item_id,
            quantity=qty,
            uom_id=item_in.uom_id,
            unit_price=price,
            subtotal=line_total
        ))

    disc = Decimal(str(data.discount_amount or 0))
    net_after_disc = subtotal - disc
    tax_pct = Decimal(str(data.tax_rate or 0))
    tax_amount = (net_after_disc * (tax_pct / Decimal('100.00'))).quantize(Decimal('0.01'))
    total_amount = net_after_disc + tax_amount

    invoice = SalesInvoice(
        invoice_number=inv_num,
        date=data.date,
        due_date=data.due_date,
        customer_id=customer.id,
        payment_terms=data.payment_terms,
        status="DRAFT",
        subtotal=subtotal,
        discount_amount=disc,
        tax_rate=tax_pct,
        tax_amount=tax_amount,
        total_amount=total_amount,
        warehouse_id=fg_wh_id,
        created_by_id=user.id,
        notes=data.notes
    )
    db.add(invoice)
    db.flush()

    for l in line_objs:
        l.invoice_id = invoice.id
        db.add(l)

    db.commit()
    db.refresh(invoice)
    return invoice.to_dict()

@router.delete("/api/invoices/{id}")
async def delete_sales_invoice(id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    invoice = db.query(SalesInvoice).filter(SalesInvoice.id == id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="الفاتورة غير موجودة")

    if invoice.status != "DRAFT":
        raise HTTPException(status_code=400, detail="لا يمكن حذف فاتورة تم اعتمادها أو ترحيل قيودها")

    db.query(SalesInvoiceItem).filter(SalesInvoiceItem.invoice_id == id).delete()
    db.delete(invoice)
    db.commit()
    return {"success": True, "message": "تم حذف الفاتورة المسودة بنجاح"}

@router.post("/api/invoices/{id}/confirm")
async def api_confirm_invoice(id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        invoice = confirm_sales_invoice(db=db, invoice_id=id, user_id=user.id)
        audit = AuditLog(
            user_id=user.id,
            action="INVOICE_CONFIRMED",
            entity_type="SalesInvoice",
            entity_id=invoice.id,
            details=f"اعتماد فاتورة مبيعات رقم {invoice.invoice_number} للعميل {invoice.customer.name_ar} بمبلغ {invoice.total_amount}"
        )
        db.add(audit)
        db.commit()
        db.refresh(invoice)
        return invoice.to_dict()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/api/invoices/export")
async def export_invoices_excel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    invoices = db.query(SalesInvoice).order_by(SalesInvoice.id.desc()).all()
    headers = [
        "رقم الفاتورة", "التاريخ", "اسم العميل", "الحالة", "المجموع الفرعي",
        "الخصم", "الضريبة", "إجمالي الفاتورة", "المدفوع", "المتبقي", "شروط السداد"
    ]
    rows = []
    status_map = {"DRAFT": "مسودة", "CONFIRMED": "معتمدة", "PAID": "مسددة بالكامل", "CANCELLED": "ملغاة"}
    for inv in invoices:
        paid = float(inv.paid_amount or 0)
        tot = float(inv.total_amount or 0)
        rows.append([
            inv.invoice_number,
            inv.date.strftime("%Y-%m-%d"),
            inv.customer.name_ar if inv.customer else "-",
            status_map.get(inv.status, inv.status),
            float(inv.subtotal or 0),
            float(inv.discount_amount or 0),
            float(inv.tax_amount or 0),
            tot,
            paid,
            round(tot - paid, 2),
            inv.payment_terms
        ])
    return create_excel_streaming_response("فواتير_المبيعات_الجملة", "الفواتير", headers, rows, "سجل فواتير مبيعات الجملة - CoffeeRoast ERP")

@router.get("/api/aging")
async def api_aging_report(as_of_date: Optional[date] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_customer_aging_report(db, as_of_date)
