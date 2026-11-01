from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models.user import User, AuditLog
from app.models.inventory import Item, Warehouse, UnitOfMeasure, StockQuant, StockMove
from app.models.accounting import Account
from app.auth import get_current_user_optional, get_current_user
from app.services.inventory_service import record_stock_movement
from app.services.excel_service import (
    create_excel_streaming_response,
    generate_items_template,
    generate_stock_balances_template,
    import_items_from_bytes,
    import_stock_balances_from_bytes
)

router = APIRouter(prefix="/inventory", tags=["Inventory & Warehouses"])

class CreateItemRequest(BaseModel):
    sku: str
    name: str
    name_ar: str
    category: str
    uom_id: int
    cost_price: float = 0.0
    selling_price: float = 0.0
    reorder_level: float = 0.0

class UpdateItemRequest(BaseModel):
    name: str
    name_ar: str
    category: str
    uom_id: int
    cost_price: float = 0.0
    selling_price: float = 0.0
    reorder_level: float = 0.0
    is_active: bool = True

class CreateWarehouseRequest(BaseModel):
    code: str
    name: str
    name_ar: str
    account_id: Optional[int] = None

class UpdateWarehouseRequest(BaseModel):
    name: str
    name_ar: str
    account_id: Optional[int] = None
    is_active: bool = True

class StockAdjustRequest(BaseModel):
    item_id: int
    warehouse_id: int
    new_quantity: float
    reason: str

# Views
@router.get("/items", response_class=HTMLResponse)
async def view_items(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="inventory/items.html", context={
        "request": request,
        "user": user,
        "active_nav": "inventory",
        "sub_nav": "items"
    })

@router.get("/warehouses", response_class=HTMLResponse)
async def view_warehouses(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="inventory/warehouses.html", context={
        "request": request,
        "user": user,
        "active_nav": "inventory",
        "sub_nav": "warehouses"
    })

@router.get("/stock-moves", response_class=HTMLResponse)
async def view_stock_moves(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="inventory/stock_moves.html", context={
        "request": request,
        "user": user,
        "active_nav": "inventory",
        "sub_nav": "stock_moves"
    })

# APIs - Items
@router.get("/api/items")
async def list_items(category: Optional[str] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Item).filter(Item.is_active == True)
    if category:
        query = query.filter(Item.category == category)
    items = query.order_by(Item.category.asc(), Item.name.asc()).all()
    
    # Calculate current stock quantity per item
    results = []
    for item in items:
        d = item.to_dict()
        quants = db.query(StockQuant).filter(StockQuant.item_id == item.id).all()
        d["total_quantity"] = round(sum([float(q.quantity or 0) for q in quants]), 2)
        results.append(d)
    return results

@router.post("/api/items")
async def create_item(data: CreateItemRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    existing = db.query(Item).filter(Item.sku == data.sku).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"كود الصنف '{data.sku}' مسجل مسبقاً")
    
    item = Item(
        sku=data.sku,
        name=data.name,
        name_ar=data.name_ar,
        category=data.category,
        uom_id=data.uom_id,
        cost_price=Decimal(str(data.cost_price)),
        selling_price=Decimal(str(data.selling_price)),
        reorder_level=Decimal(str(data.reorder_level))
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item.to_dict()

@router.put("/api/items/{id}")
async def update_item(id: int, data: UpdateItemRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="الصنف غير موجود")
    
    item.name = data.name
    item.name_ar = data.name_ar
    item.category = data.category
    item.uom_id = data.uom_id
    item.cost_price = Decimal(str(data.cost_price))
    item.selling_price = Decimal(str(data.selling_price))
    item.reorder_level = Decimal(str(data.reorder_level))
    item.is_active = data.is_active
    db.commit()
    db.refresh(item)
    return item.to_dict()

@router.delete("/api/items/{id}")
async def delete_item(id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="الصنف غير موجود")
    
    # Check if stock movements exist
    has_moves = db.query(StockMove).filter(StockMove.item_id == id).first()
    if has_moves:
        item.is_active = False
        db.commit()
        return {"success": True, "message": "تم تعطيل الصنف لوجود حركات مخزنية مرتبطة به"}

    db.delete(item)
    db.commit()
    return {"success": True, "message": "تم حذف الصنف بنجاح"}

# Excel Export & Import for Items
@router.get("/api/items/export")
async def export_items_excel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Item).all()
    headers = [
        "كود الصنف SKU", "الاسم بالعربية", "الاسم بالإنجليزية", "التصنيف",
        "الوحدة", "سعر التكلفة", "سعر البيع", "الرصيد الإجمالي", "حد إعادة الطلب"
    ]
    rows = []
    cat_names = {
        "RAW_COFFEE": "بن أخضر خام",
        "ROASTED_COFFEE": "بن محمص ومطحون",
        "SPICE": "بهارات وإضافات",
        "PACKAGING": "مواد تعبئة وتغليف",
        "FINISHED_GOODS": "منتجات تامة الصنع"
    }
    for item in items:
        quants = db.query(StockQuant).filter(StockQuant.item_id == item.id).all()
        tot_qty = sum([float(q.quantity or 0) for q in quants])
        rows.append([
            item.sku,
            item.name_ar,
            item.name,
            cat_names.get(item.category, item.category),
            item.uom.name_ar if item.uom else "-",
            float(item.cost_price or 0),
            float(item.selling_price or 0),
            round(tot_qty, 2),
            float(item.reorder_level or 0)
        ])
    return create_excel_streaming_response("دليل_الأصناف_والمخزون", "الأصناف", headers, rows, "دليل الأصناف والمنتجات - CoffeeRoast ERP")

@router.get("/api/items/template")
async def get_items_template(user: User = Depends(get_current_user)):
    return generate_items_template()

@router.post("/api/items/import")
async def import_items(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    content = await file.read()
    try:
        return import_items_from_bytes(content, file.filename, db, user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"فشل استيراد الأصناف: {str(e)}")

# Initial Inventory Import & Template
@router.get("/api/inventory/template-balances")
@router.get("/api/inventory/initial-balances-template")
async def get_balances_template(user: User = Depends(get_current_user)):
    return generate_stock_balances_template()

@router.post("/api/inventory/import-balances")
async def import_initial_balances(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    content = await file.read()
    try:
        return import_stock_balances_from_bytes(content, file.filename, db, user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"فشل استيراد الأرصدة الافتتاحية: {str(e)}")

# Warehouses APIs
@router.get("/api/warehouses")
async def list_warehouses(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    warehouses = db.query(Warehouse).all()
    result = []
    for wh in warehouses:
        wh_dict = wh.to_dict()
        quants = db.query(StockQuant).filter(StockQuant.warehouse_id == wh.id).all()
        total_value = sum([float(q.quantity or 0) * float(q.item.cost_price or 0) for q in quants if q.item])
        wh_dict["total_items_count"] = len(quants)
        wh_dict["valuation"] = round(total_value, 2)
        wh_dict["quants"] = [q.to_dict() for q in quants]
        result.append(wh_dict)
    return result

@router.post("/api/warehouses")
async def create_warehouse(data: CreateWarehouseRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    existing = db.query(Warehouse).filter(Warehouse.code == data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"كود المستودع '{data.code}' موجود مسبقاً")
    wh = Warehouse(code=data.code, name=data.name, name_ar=data.name_ar, account_id=data.account_id)
    db.add(wh)
    db.commit()
    db.refresh(wh)
    return wh.to_dict()

@router.put("/api/warehouses/{id}")
async def update_warehouse(id: int, data: UpdateWarehouseRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wh = db.query(Warehouse).filter(Warehouse.id == id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="المستودع غير موجود")
    wh.name = data.name
    wh.name_ar = data.name_ar
    wh.account_id = data.account_id
    wh.is_active = data.is_active
    db.commit()
    db.refresh(wh)
    return wh.to_dict()

@router.get("/api/uoms")
async def list_uoms(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    uoms = db.query(UnitOfMeasure).all()
    return [u.to_dict() for u in uoms]

@router.get("/api/stock-moves")
async def list_stock_moves(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    moves = db.query(StockMove).order_by(StockMove.id.desc()).limit(200).all()
    return [m.to_dict() for m in moves]

@router.get("/api/stock-moves/export")
async def export_stock_moves_excel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    moves = db.query(StockMove).order_by(StockMove.id.desc()).limit(500).all()
    headers = ["رقم الحركة", "التاريخ والوقت", "نوع الحركة", "الصنف", "من مستودع", "إلى مستودع", "الكمية", "تكلفة الوحدة", "الإجمالي", "المرجع"]
    rows = []
    type_map = {
        "PURCHASE_RECEIPT": "استلام مشتريات",
        "ROASTING_CONSUME": "صرف للتحميص",
        "ROASTING_OUTPUT": "إنتاج محمص",
        "BOM_CONSUME": "صرف للخلط والتعبئة",
        "BOM_OUTPUT": "إنتاج تام معبأ",
        "SALES_DELIVERY": "تسليم مبيعات",
        "ADJUSTMENT": "تسوية جردية",
        "OPENING_BALANCE": "رصيد افتتاحي"
    }
    for m in moves:
        rows.append([
            m.move_number,
            m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else "-",
            type_map.get(m.move_type, m.move_type),
            m.item.name_ar if m.item else "-",
            m.from_warehouse.name_ar if m.from_warehouse else "-",
            m.to_warehouse.name_ar if m.to_warehouse else "-",
            float(m.quantity or 0),
            float(m.unit_cost or 0),
            round(float(m.quantity or 0) * float(m.unit_cost or 0), 2),
            m.reference or "-"
        ])
    return create_excel_streaming_response("سجل_حركات_المخزون", "حركات المخزون", headers, rows, "سجل حركة المخزون العام - CoffeeRoast ERP")

@router.post("/api/adjust")
async def adjust_stock(data: StockAdjustRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    quant = db.query(StockQuant).filter(
        StockQuant.item_id == data.item_id,
        StockQuant.warehouse_id == data.warehouse_id
    ).first()

    old_qty = Decimal(str(quant.quantity or 0)) if quant else Decimal('0.0000')
    target_qty = Decimal(str(data.new_quantity))
    diff = target_qty - old_qty

    item = db.query(Item).filter(Item.id == data.item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="الصنف غير موجود")

    if diff > 0:
        record_stock_movement(
            db=db,
            item_id=item.id,
            from_warehouse_id=None,
            to_warehouse_id=data.warehouse_id,
            quantity=diff,
            uom_id=item.uom_id,
            unit_cost=Decimal(str(item.cost_price or 0)),
            move_type="ADJUSTMENT",
            reference=f"تسوية جردية: {data.reason}",
            created_by_id=user.id
        )
    elif diff < 0:
        record_stock_movement(
            db=db,
            item_id=item.id,
            from_warehouse_id=data.warehouse_id,
            to_warehouse_id=None,
            quantity=abs(diff),
            uom_id=item.uom_id,
            unit_cost=Decimal(str(item.cost_price or 0)),
            move_type="ADJUSTMENT",
            reference=f"تسوية جردية: {data.reason}",
            created_by_id=user.id
        )

    db.commit()
    return {"success": True, "message": "تمت التسوية الجردية للمخزون بنجاح"}
