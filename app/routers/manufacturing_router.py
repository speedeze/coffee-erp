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
from app.models.manufacturing import RoastingOrder, Recipe, RecipeItem, ProductionOrder
from app.models.inventory import Item, Warehouse
from app.auth import get_current_user_optional, get_current_user
from app.services.manufacturing_service import complete_roasting_order, complete_production_order
from app.services.excel_service import create_excel_streaming_response

router = APIRouter(prefix="/manufacturing", tags=["Roasting & Manufacturing"])

class CreateRoastingOrderRequest(BaseModel):
    date: date
    roast_profile: str = "Medium"
    raw_item_id: int
    raw_quantity_kg: float
    expected_shrinkage_pct: float = 18.0
    notes: Optional[str] = None

class CompleteRoastRequest(BaseModel):
    actual_roasted_qty_kg: float
    additional_cost: float = 0.0

class RecipeItemInput(BaseModel):
    item_id: int
    quantity: float
    uom_id: int
    notes: Optional[str] = None

class CreateRecipeRequest(BaseModel):
    code: str
    name: str
    name_ar: str
    finished_item_id: int
    yield_quantity: float = 1.0
    yield_uom_id: int
    description: Optional[str] = None
    items: List[RecipeItemInput]

class UpdateRecipeRequest(BaseModel):
    name: str
    name_ar: str
    yield_quantity: float = 1.0
    description: Optional[str] = None
    is_active: bool = True

class CreateProductionOrderRequest(BaseModel):
    date: date
    recipe_id: int
    target_quantity: float
    notes: Optional[str] = None

# Views
@router.get("/roasting", response_class=HTMLResponse)
async def view_roasting(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="manufacturing/roasting.html", context={
        "request": request,
        "user": user,
        "active_nav": "manufacturing",
        "sub_nav": "roasting"
    })

@router.get("/recipes", response_class=HTMLResponse)
async def view_recipes(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="manufacturing/recipes.html", context={
        "request": request,
        "user": user,
        "active_nav": "manufacturing",
        "sub_nav": "recipes"
    })

@router.get("/production", response_class=HTMLResponse)
async def view_production(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.main import templates
    return templates.TemplateResponse(request=request, name="manufacturing/production.html", context={
        "request": request,
        "user": user,
        "active_nav": "manufacturing",
        "sub_nav": "production"
    })

# APIs - Roasting
@router.get("/api/roasting")
async def list_roasting_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    orders = db.query(RoastingOrder).order_by(RoastingOrder.id.desc()).all()
    return [o.to_dict() for o in orders]

@router.post("/api/roasting")
async def create_roasting_order(data: CreateRoastingOrderRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    raw_item = db.query(Item).filter(Item.id == data.raw_item_id).first()
    if not raw_item:
        raise HTTPException(status_code=404, detail="صنف البن الأخضر غير موجود")

    wh_raw = db.query(Warehouse).filter(Warehouse.code == "WH-RAW").first()
    wh_roast = db.query(Warehouse).filter(Warehouse.code == "WH-ROAST").first()

    # Find matching roasted item
    roast_sku_prefix = raw_item.sku.replace("RAW-", "ROAST-")
    roasted_item = db.query(Item).filter(Item.sku.like(f"{roast_sku_prefix}%")).first()
    if not roasted_item:
        roasted_item = db.query(Item).filter(Item.category == "ROASTED_COFFEE").first()

    count = db.query(func.count(RoastingOrder.id)).scalar() or 0
    order_num = f"ROAST-{date.today().year}-{(count + 1):04d}"

    raw_qty = Decimal(str(data.raw_quantity_kg))
    raw_cost = Decimal(str(raw_item.cost_price or 0))
    tot_raw_cost = raw_qty * raw_cost

    order = RoastingOrder(
        order_number=order_num,
        date=data.date,
        status="DRAFT",
        roast_profile=data.roast_profile,
        raw_item_id=raw_item.id,
        raw_warehouse_id=wh_raw.id,
        raw_quantity_kg=raw_qty,
        raw_unit_cost=raw_cost,
        total_raw_cost=tot_raw_cost,
        roasted_item_id=roasted_item.id if roasted_item else raw_item.id,
        roasted_warehouse_id=wh_roast.id,
        expected_shrinkage_pct=Decimal(str(data.expected_shrinkage_pct)),
        created_by_id=user.id,
        notes=data.notes
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order.to_dict()

@router.delete("/api/roasting/{id}")
async def delete_roasting_order(id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(RoastingOrder).filter(RoastingOrder.id == id).first()
    if not order:
        raise HTTPException(status_code=404, detail="أمر التحميص غير موجود")
    if order.status != "DRAFT":
        raise HTTPException(status_code=400, detail="لا يمكن حذف أمر تحميص تم إتمامه وترحيل قيده")
    db.delete(order)
    db.commit()
    return {"success": True, "message": "تم حذف أمر التحميص المسودة بنجاح"}

@router.post("/api/roasting/{id}/complete")
async def api_complete_roast(id: int, data: CompleteRoastRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        order = complete_roasting_order(
            db=db,
            order_id=id,
            actual_roasted_qty_kg=Decimal(str(data.actual_roasted_qty_kg)),
            additional_cost=Decimal(str(data.additional_cost or 0)),
            user_id=user.id
        )
        audit = AuditLog(
            user_id=user.id,
            action="ROASTING_COMPLETED",
            entity_type="RoastingOrder",
            entity_id=order.id,
            details=f"إتمام أمر تحميص {order.order_number}: مدخل {order.raw_quantity_kg} كجم -> ناتج {order.actual_roasted_qty_kg} كجم، نسبة الهالك {order.actual_shrinkage_pct}%"
        )
        db.add(audit)
        db.commit()
        db.refresh(order)
        return order.to_dict()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/api/roasting/export")
async def export_roasting_excel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    orders = db.query(RoastingOrder).order_by(RoastingOrder.id.desc()).all()
    headers = [
        "رقم الأمر", "التاريخ", "الحالة", "درجة التحميص", "البن الأخضر الخام",
        "الكمية الخام (كجم)", "الناتج الفعلي (كجم)", "نسبة الهالك %", "فقد الوزن (كجم)",
        "تكلفة الكيلو بعد التحميص", "إجمالي تكلفة الوجبة"
    ]
    rows = []
    status_map = {"DRAFT": "مسودة", "IN_PROGRESS": "قيد التشغيل", "COMPLETED": "مكتمل ومرحل", "CANCELLED": "ملغي"}
    for o in orders:
        rows.append([
            o.order_number,
            o.date.strftime("%Y-%m-%d"),
            status_map.get(o.status, o.status),
            o.roast_profile,
            o.raw_item.name_ar if o.raw_item else "-",
            float(o.raw_quantity_kg or 0),
            float(o.actual_roasted_qty_kg or 0),
            float(o.actual_shrinkage_pct or 0),
            float(o.shrinkage_loss_kg or 0),
            float(o.revalued_cost_per_kg or 0),
            float(o.total_production_cost or o.total_raw_cost or 0)
        ])
    return create_excel_streaming_response("أوامر_التحميص_والهالك", "التحميص", headers, rows, "سجل تشغيل المحامص الصناعية وحساب الهالك والتكلفة")

# APIs - Recipes & Production
@router.get("/api/recipes")
async def list_recipes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    recipes = db.query(Recipe).filter(Recipe.is_active == True).all()
    return [r.to_dict() for r in recipes]

@router.post("/api/recipes")
async def create_recipe(data: CreateRecipeRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    existing = db.query(Recipe).filter(Recipe.code == data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"كود الوصفة '{data.code}' موجود مسبقاً")

    recipe = Recipe(
        code=data.code,
        name=data.name,
        name_ar=data.name_ar,
        finished_item_id=data.finished_item_id,
        yield_quantity=Decimal(str(data.yield_quantity)),
        yield_uom_id=data.yield_uom_id,
        description=data.description
    )
    db.add(recipe)
    db.flush()

    for itm in data.items:
        r_item = RecipeItem(
            recipe_id=recipe.id,
            item_id=itm.item_id,
            quantity=Decimal(str(itm.quantity)),
            uom_id=itm.uom_id,
            notes=itm.notes
        )
        db.add(r_item)

    db.commit()
    db.refresh(recipe)
    return recipe.to_dict()

@router.put("/api/recipes/{id}")
async def update_recipe(id: int, data: UpdateRecipeRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    recipe = db.query(Recipe).filter(Recipe.id == id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="الوصفة غير موجودة")
    recipe.name = data.name
    recipe.name_ar = data.name_ar
    recipe.yield_quantity = Decimal(str(data.yield_quantity))
    recipe.description = data.description
    recipe.is_active = data.is_active
    db.commit()
    db.refresh(recipe)
    return recipe.to_dict()

@router.delete("/api/recipes/{id}")
async def delete_recipe(id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    recipe = db.query(Recipe).filter(Recipe.id == id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="الوصفة غير موجودة")
    recipe.is_active = False
    db.commit()
    return {"success": True, "message": "تم تعطيل الوصفة بنجاح"}

@router.get("/api/production")
async def list_production_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    orders = db.query(ProductionOrder).order_by(ProductionOrder.id.desc()).all()
    return [o.to_dict() for o in orders]

@router.post("/api/production")
async def create_production_order(data: CreateProductionOrderRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    recipe = db.query(Recipe).filter(Recipe.id == data.recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="التركيبة BOM غير موجودة")

    wh_fg = db.query(Warehouse).filter(Warehouse.code == "WH-FG").first()
    count = db.query(func.count(ProductionOrder.id)).scalar() or 0
    order_num = f"PROD-{date.today().year}-{(count + 1):04d}"

    order = ProductionOrder(
        order_number=order_num,
        date=data.date,
        recipe_id=recipe.id,
        target_quantity=Decimal(str(data.target_quantity)),
        status="DRAFT",
        destination_warehouse_id=wh_fg.id,
        created_by_id=user.id,
        notes=data.notes
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order.to_dict()

@router.delete("/api/production/{id}")
async def delete_production_order(id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(ProductionOrder).filter(ProductionOrder.id == id).first()
    if not order:
        raise HTTPException(status_code=404, detail="أمر التعبئة غير موجود")
    if order.status != "DRAFT":
        raise HTTPException(status_code=400, detail="لا يمكن حذف أمر إنتاج تم تنفيذه")
    db.delete(order)
    db.commit()
    return {"success": True, "message": "تم حذف أمر التعبئة المسودة بنجاح"}

@router.post("/api/production/{id}/complete")
async def api_complete_production(id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        order = complete_production_order(db=db, order_id=id, user_id=user.id)
        audit = AuditLog(
            user_id=user.id,
            action="PRODUCTION_COMPLETED",
            entity_type="ProductionOrder",
            entity_id=order.id,
            details=f"إتمام أمر خلط وتعبئة {order.order_number} لوصفة {order.recipe.name_ar}: إنتاج {order.target_quantity} عبوة، التكلفة ${order.total_cost}"
        )
        db.add(audit)
        db.commit()
        db.refresh(order)
        return order.to_dict()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/api/production/export")
async def export_production_excel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    orders = db.query(ProductionOrder).order_by(ProductionOrder.id.desc()).all()
    headers = ["رقم الأمر", "التاريخ", "الحالة", "التركيبة BOM", "المنتج التام", "الكمية المنتجة", "إجمالي التكلفة", "تكلفة العبوة"]
    rows = []
    status_map = {"DRAFT": "مسودة", "COMPLETED": "مكتمل ومنجز", "CANCELLED": "ملغي"}
    for o in orders:
        rows.append([
            o.order_number,
            o.date.strftime("%Y-%m-%d"),
            status_map.get(o.status, o.status),
            o.recipe.name_ar if o.recipe else "-",
            o.recipe.finished_item.name_ar if o.recipe and o.recipe.finished_item else "-",
            float(o.target_quantity or 0),
            float(o.total_cost or 0),
            float(o.unit_cost or 0)
        ])
    return create_excel_streaming_response("أوامر_الخلط_والتعبئة", "أوامر الإنتاج", headers, rows, "سجل تشغيل خطوط الخلط والتعبئة والتغليف")
