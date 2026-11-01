from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.inventory import Item, UnitOfMeasure, Warehouse, StockQuant, StockMove

def convert_quantity(
    quantity: Decimal,
    from_uom: UnitOfMeasure,
    to_uom: UnitOfMeasure
) -> Decimal:
    """Converts quantity between units of measure using ratio to base."""
    if from_uom.id == to_uom.id:
        return quantity
    if from_uom.category != to_uom.category:
        raise ValueError(f"Cannot convert between {from_uom.category} and {to_uom.category}")
    
    # Convert to base, then to target
    base_qty = quantity * Decimal(str(from_uom.ratio_to_base))
    target_qty = base_qty / Decimal(str(to_uom.ratio_to_base))
    return target_qty

def get_or_create_quant(db: Session, item_id: int, warehouse_id: int) -> StockQuant:
    quant = db.query(StockQuant).filter(
        StockQuant.item_id == item_id,
        StockQuant.warehouse_id == warehouse_id
    ).first()
    if not quant:
        quant = StockQuant(
            item_id=item_id,
            warehouse_id=warehouse_id,
            quantity=Decimal('0.0000'),
            reserved_quantity=Decimal('0.0000')
        )
        db.add(quant)
        db.flush()
    return quant

def update_item_weighted_cost(
    db: Session,
    item: Item,
    new_quantity: Decimal,
    new_unit_cost: Decimal
):
    """
    Recalculates Weighted Average Cost (WAC) per base unit when new inventory arrives.
    """
    total_existing_stock = db.query(
        func.coalesce(func.sum(StockQuant.quantity), 0)
    ).filter(StockQuant.item_id == item.id).scalar() or Decimal('0')
    
    existing_qty = Decimal(str(total_existing_stock))
    current_cost = Decimal(str(item.cost_price or 0))

    if existing_qty <= 0:
        item.cost_price = new_unit_cost
    else:
        total_existing_value = existing_qty * current_cost
        total_new_value = new_quantity * new_unit_cost
        total_combined_qty = existing_qty + new_quantity
        if total_combined_qty > 0:
            item.cost_price = (total_existing_value + total_new_value) / total_combined_qty

    db.flush()

def record_stock_movement(
    db: Session,
    item_id: int,
    from_warehouse_id: Optional[int],
    to_warehouse_id: Optional[int],
    quantity: Decimal,
    uom_id: int,
    unit_cost: Decimal,
    move_type: str,
    reference: Optional[str] = None,
    created_by_id: Optional[int] = None,
    journal_entry_id: Optional[int] = None
) -> StockMove:
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise ValueError("Item not found")

    uom = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == uom_id).first()
    if not uom:
        raise ValueError("UOM not found")

    # Convert to item's base UOM
    base_quantity = quantity * Decimal(str(uom.ratio_to_base))
    total_cost = (base_quantity * unit_cost).quantize(Decimal('0.01'))

    # Deduct from source warehouse
    if from_warehouse_id:
        src_quant = get_or_create_quant(db, item_id, from_warehouse_id)
        if Decimal(str(src_quant.quantity or 0)) < base_quantity:
            raise ValueError(
                f"Insufficient stock for '{item.name}' in warehouse! "
                f"Available: {src_quant.quantity}, Requested: {base_quantity}"
            )
        src_quant.quantity = Decimal(str(src_quant.quantity or 0)) - base_quantity

    # Add to destination warehouse
    if to_warehouse_id:
        dest_quant = get_or_create_quant(db, item_id, to_warehouse_id)
        dest_quant.quantity = Decimal(str(dest_quant.quantity or 0)) + base_quantity

    # Generate sequential move number
    move_count = db.query(func.count(StockMove.id)).scalar() or 0
    move_number = f"SM-{datetime.utcnow().year}-{(move_count + 1):05d}"

    move = StockMove(
        move_number=move_number,
        date=datetime.utcnow(),
        item_id=item_id,
        from_warehouse_id=from_warehouse_id,
        to_warehouse_id=to_warehouse_id,
        quantity=quantity,
        uom_id=uom_id,
        unit_cost=unit_cost,
        total_cost=total_cost,
        reference=reference,
        move_type=move_type,
        journal_entry_id=journal_entry_id,
        created_by_id=created_by_id
    )
    db.add(move)
    db.flush()
    return move
