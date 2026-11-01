from datetime import date
from decimal import Decimal
from typing import Optional, List
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from app.database import get_db
from app.models.user import User, AuditLog
from app.models.purchase import Supplier, PurchaseOrder, PurchaseOrderItem, LandedCost
from app.models.inventory import Warehouse
from app.auth import get_current_user_optional, get_current_user
from app.services.purchase_service import receive_purchase_shipment
from app.services.excel_service import create_excel_streaming_response

router = APIRouter(prefix="/purchases", tags=["Purchases & Imports"])

class CreateSupplierRequest(BaseModel):
    code: str
    name: str
    name_ar: str
    country: str = "Local"
    is_foreign: bool = False
    currency: str = "USD"
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None

class UpdateSupplierRequest(BaseModel):
    name: str
    name_ar: str
    country: str = "Local"
    is_foreign: bool = False
    currency: str = "USD"
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    is_active: bool = True

class PurchaseItemInput(BaseModel):
    item_id: int
    quantity: float
    uom_id: int
    unit_price: float

class LandedCostInput(BaseModel):
    cost_type: str
    cost_type_ar: str
    amount: float
    vendor_name: Optional[str] = None
    allocation_method: str = "WEIGHT"
    notes: Optional[str] = None

class CreatePurchaseOrderRequest(BaseModel):
    date: date
    supplier_id: int
    bill_of_lading: Optional[str] = None
    currency: str = "USD"
    exchange_rate: float = 1.0
    warehouse_id: Optional[int] = None
    notes: Optional[str] = None
    items: List[PurchaseItemInput]
    landed_costs: Optional[List[LandedCostInput]] = []

# Views
@router.get("/suppliers", response_class=HTMLResponse)
async def view_suppliers(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="purchases/suppliers.html", context={
        "request": request,
        "user": user,
        "active_nav": "purchases",
        "sub_nav": "suppliers"
    })

@router.get("/orders", response_class=HTMLResponse)
async def view_orders(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="purchases/orders.html", context={
        "request": request,
        "user": user,
        "active_nav": "purchases",
        "sub_nav": "orders"
    })

# APIs - Suppliers
@router.get("/api/suppliers")
async def list_suppliers(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    suppliers = db.query(Supplier).filter(Supplier.is_active == True).order_by(Supplier.id.desc()).all()
    return [s.to_dict() for s in suppliers]

@router.post("/api/suppliers")
async def create_supplier(data: CreateSupplierRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    existing = db.query(Supplier).filter(Supplier.code == data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"كود المورد '{data.code}' موجود مسبقاً")

    supplier = Supplier(
        code=data.code,
        name=data.name,
        name_ar=data.name_ar,
        country=data.country,
        is_foreign=data.is_foreign,
        currency=data.currency,
        phone=data.phone,
        email=data.email,
        address=data.address
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier.to_dict()

@router.put("/api/suppliers/{id}")
async def update_supplier(id: int, data: UpdateSupplierRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    supplier = db.query(Supplier).filter(Supplier.id == id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="المورد غير موجود")

    supplier.name = data.name
    supplier.name_ar = data.name_ar
    supplier.country = data.country
    supplier.is_foreign = data.is_foreign
    supplier.currency = data.currency
    supplier.phone = data.phone
    supplier.email = data.email
    supplier.address = data.address
    supplier.is_active = data.is_active
    db.commit()
    db.refresh(supplier)
    return supplier.to_dict()

@router.delete("/api/suppliers/{id}")
async def delete_supplier(id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    supplier = db.query(Supplier).filter(Supplier.id == id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="المورد غير موجود")

    has_orders = db.query(PurchaseOrder).filter(PurchaseOrder.supplier_id == id).first()
    if has_orders:
        supplier.is_active = False
        db.commit()
        return {"success": True, "message": "تم تعطيل المورد لوجود أوامر شراء سابقة"}

    db.delete(supplier)
    db.commit()
    return {"success": True, "message": "تم حذف المورد بنجاح"}

@router.get("/api/suppliers/export")
async def export_suppliers_excel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    suppliers = db.query(Supplier).all()
    headers = ["كود المورد", "الاسم بالعربية", "الاسم بالإنجليزية", "الدولة", "استيراد خارجي", "العملة", "الهاتف", "البريد الإلكتروني", "الحالة"]
    rows = []
    for s in suppliers:
        rows.append([
            s.code,
            s.name_ar,
            s.name,
            s.country,
            "نعم (دولي)" if s.is_foreign else "محلي",
            s.currency,
            s.phone or "-",
            s.email or "-",
            "نشط" if s.is_active else "معطل"
        ])
    return create_excel_streaming_response("دليل_الموردين", "الموردين", headers, rows, "سجل الموردين وشركات الاستيراد - CoffeeRoast ERP")

# Purchase Orders APIs
@router.get("/api/orders")
async def list_purchase_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    orders = db.query(PurchaseOrder).order_by(PurchaseOrder.id.desc()).all()
    return [o.to_dict() for o in orders]

@router.post("/api/orders")
async def create_purchase_order(data: CreatePurchaseOrderRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    supplier = db.query(Supplier).filter(Supplier.id == data.supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="المورد غير موجود")

    dest_wh = data.warehouse_id
    if not dest_wh:
        wh = db.query(Warehouse).filter(Warehouse.code == "WH-RAW").first()
        dest_wh = wh.id

    count = db.query(func.count(PurchaseOrder.id)).scalar() or 0
    po_num = f"PO-{date.today().year}-{(count + 1):04d}"

    total_fob = Decimal('0.00')
    total_weight = Decimal('0.00')
    line_objs = []
    for item_in in data.items:
        qty = Decimal(str(item_in.quantity))
        price = Decimal(str(item_in.unit_price))
        line_total = (qty * price).quantize(Decimal('0.01'))
        total_fob += line_total
        total_weight += qty

        line_objs.append(PurchaseOrderItem(
            item_id=item_in.item_id,
            quantity=qty,
            uom_id=item_in.uom_id,
            unit_price_fob=price,
            total_fob_price=line_total
        ))

    total_landed = Decimal('0.00')
    landed_objs = []
    if data.landed_costs:
        for lc in data.landed_costs:
            amt = Decimal(str(lc.amount)).quantize(Decimal('0.01'))
            total_landed += amt
            landed_objs.append(LandedCost(
                cost_type=lc.cost_type,
                cost_type_ar=lc.cost_type_ar,
                amount=amt,
                vendor_name=lc.vendor_name,
                allocation_method=lc.allocation_method,
                notes=lc.notes
            ))

    total_actual = total_fob + total_landed

    order = PurchaseOrder(
        order_number=po_num,
        date=data.date,
        supplier_id=supplier.id,
        bill_of_lading=data.bill_of_lading,
        currency=data.currency,
        exchange_rate=Decimal(str(data.exchange_rate)),
        status="DRAFT",
        total_fob_amount=total_fob,
        total_landed_costs=total_landed,
        total_actual_cost=total_actual,
        destination_warehouse_id=dest_wh,
        created_by_id=user.id,
        notes=data.notes
    )
    db.add(order)
    db.flush()

    for l in line_objs:
        l.order_id = order.id
        db.add(l)

    for lc in landed_objs:
        lc.order_id = order.id
        db.add(lc)

    db.commit()
    db.refresh(order)
    return order.to_dict()

@router.delete("/api/orders/{id}")
async def delete_purchase_order(id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(PurchaseOrder).filter(PurchaseOrder.id == id).first()
    if not order:
        raise HTTPException(status_code=404, detail="أمر الشراء غير موجود")

    if order.status != "DRAFT":
        raise HTTPException(status_code=400, detail="لا يمكن حذف شحنة تم استلامها وتوليد قيودها المحاسبية")

    db.query(LandedCost).filter(LandedCost.order_id == id).delete()
    db.query(PurchaseOrderItem).filter(PurchaseOrderItem.order_id == id).delete()
    db.delete(order)
    db.commit()
    return {"success": True, "message": "تم حذف أمر الشراء المسودة بنجاح"}

@router.post("/api/orders/{id}/receive")
async def api_receive_order(id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        order = receive_purchase_shipment(db=db, order_id=id, user_id=user.id)
        audit = AuditLog(
            user_id=user.id,
            action="PURCHASE_RECEIVED",
            entity_type="PurchaseOrder",
            entity_id=order.id,
            details=f"استلام وتفريغ شحنة البن رقم {order.order_number} وتوزيع التكاليف المضافة ({order.total_actual_cost}$)"
        )
        db.add(audit)
        db.commit()
        db.refresh(order)
        return order.to_dict()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/api/orders/export")
async def export_orders_excel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    orders = db.query(PurchaseOrder).order_by(PurchaseOrder.id.desc()).all()
    headers = [
        "رقم الشحنة/الأمر", "التاريخ", "المورد", "بوليصة الشحن", "الحالة",
        "قيمة البضاعة FOB", "المصاريف الإضافية (الشحن/الجمارك)", "إجمالي التكلفة الواصلة", "العملة"
    ]
    rows = []
    status_map = {"DRAFT": "مسودة", "PORT_ARRIVED": "بالميناء", "RECEIVED": "تم الاستلام بالمستودع", "CANCELLED": "ملغي"}
    for o in orders:
        rows.append([
            o.order_number,
            o.date.strftime("%Y-%m-%d"),
            o.supplier.name_ar if o.supplier else "-",
            o.bill_of_lading or "-",
            status_map.get(o.status, o.status),
            float(o.total_fob_amount or 0),
            float(o.total_landed_costs or 0),
            float(o.total_actual_cost or 0),
            o.currency
        ])
    return create_excel_streaming_response("شحنات_وأوامر_الشراء", "أوامر الشراء", headers, rows, "سجل استيراد وشحنات البن الخارجي والمحلي")
