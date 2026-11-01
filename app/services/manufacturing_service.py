from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.models.manufacturing import RoastingOrder, Recipe, ProductionOrder
from app.models.accounting import Account
from app.models.inventory import Item, Warehouse
from app.services.inventory_service import record_stock_movement, update_item_weighted_cost
from app.services.accounting_service import create_balanced_journal_entry

def complete_roasting_order(
    db: Session,
    order_id: int,
    actual_roasted_qty_kg: Decimal,
    additional_cost: Decimal = Decimal('0.00'),
    user_id: Optional[int] = None
) -> RoastingOrder:
    order = db.query(RoastingOrder).filter(RoastingOrder.id == order_id).first()
    if not order:
        raise ValueError("Roasting order not found")
    if order.status == "COMPLETED":
        raise ValueError("Roasting order is already completed")

    raw_qty = Decimal(str(order.raw_quantity_kg))
    if actual_roasted_qty_kg <= 0 or actual_roasted_qty_kg >= raw_qty:
        raise ValueError(
            f"Invalid roasted quantity {actual_roasted_qty_kg} kg. "
            f"Roasting shrinkage must yield an output less than raw input ({raw_qty} kg) and greater than zero."
        )

    # Calculate Shrinkage & Loss
    shrinkage_loss_kg = raw_qty - actual_roasted_qty_kg
    shrinkage_pct = ((shrinkage_loss_kg / raw_qty) * Decimal('100.00')).quantize(Decimal('0.01'))
    
    # Calculate Capitalized Production Cost
    total_raw_cost = Decimal(str(order.total_raw_cost))
    total_cost = total_raw_cost + additional_cost
    revalued_cost_per_kg = (total_cost / actual_roasted_qty_kg).quantize(Decimal('0.0001'))

    order.actual_roasted_qty_kg = actual_roasted_qty_kg
    order.actual_shrinkage_pct = shrinkage_pct
    order.shrinkage_loss_kg = shrinkage_loss_kg
    order.additional_cost = additional_cost
    order.total_production_cost = total_cost
    order.revalued_cost_per_kg = revalued_cost_per_kg
    order.status = "COMPLETED"
    order.completed_at = datetime.utcnow()

    # 1. Deduct raw coffee from Raw Warehouse
    raw_item = order.raw_item
    record_stock_movement(
        db=db,
        item_id=raw_item.id,
        from_warehouse_id=order.raw_warehouse_id,
        to_warehouse_id=None,
        quantity=raw_qty,
        uom_id=raw_item.uom_id,
        unit_cost=Decimal(str(order.raw_unit_cost)),
        move_type="ROASTING_INPUT",
        reference=order.order_number,
        created_by_id=user_id
    )

    # 2. Add roasted coffee to Roasted Warehouse
    roasted_item = order.roasted_item
    record_stock_movement(
        db=db,
        item_id=roasted_item.id,
        from_warehouse_id=None,
        to_warehouse_id=order.roasted_warehouse_id,
        quantity=actual_roasted_qty_kg,
        uom_id=roasted_item.uom_id,
        unit_cost=revalued_cost_per_kg,
        move_type="ROASTING_OUTPUT",
        reference=order.order_number,
        created_by_id=user_id
    )

    # Update roasted item weighted average cost
    update_item_weighted_cost(db, roasted_item, actual_roasted_qty_kg, revalued_cost_per_kg)

    # 3. Post Automated Double-Entry Journal Entry
    # Accounts:
    # Debit: Roasted Coffee Inventory (Asset)
    # Credit: Raw Coffee Inventory (Asset)
    # Credit: Direct Roasting Utilities / Absorbed Costs (if any)
    raw_acc = db.query(Account).filter(Account.code == "1310").first()  # Raw Coffee
    roasted_acc = db.query(Account).filter(Account.code == "1320").first()  # Roasted Coffee
    utilities_acc = db.query(Account).filter(Account.code == "5220").first() or db.query(Account).filter(Account.code == "2130").first()

    journal_lines = [
        {
            "account_id": roasted_acc.id,
            "debit": total_cost,
            "credit": Decimal('0.00'),
            "description": f"Roast Order {order.order_number}: {actual_roasted_qty_kg}kg roasted @ {revalued_cost_per_kg}/kg"
        },
        {
            "account_id": raw_acc.id,
            "debit": Decimal('0.00'),
            "credit": total_raw_cost,
            "description": f"Roast Order {order.order_number}: Raw beans consumed ({raw_qty}kg)"
        }
    ]

    if additional_cost > Decimal('0.00') and utilities_acc:
        journal_lines.append({
            "account_id": utilities_acc.id,
            "debit": Decimal('0.00'),
            "credit": additional_cost,
            "description": f"Roasting utilities & labor absorbed for {order.order_number}"
        })

    journal_entry = create_balanced_journal_entry(
        db=db,
        entry_date=order.date,
        reference=order.order_number,
        source_document="ROASTING",
        source_id=order.id,
        narration=f"Roasting & Grinding Order {order.order_number} - Yield {actual_roasted_qty_kg}kg ({shrinkage_pct}% moisture shrinkage)",
        lines=journal_lines,
        created_by_id=user_id
    )
    order.journal_entry_id = journal_entry.id

    db.flush()
    return order

def complete_production_order(
    db: Session,
    production_order_id: int,
    user_id: Optional[int] = None
) -> ProductionOrder:
    p_order = db.query(ProductionOrder).filter(ProductionOrder.id == production_order_id).first()
    if not p_order:
        raise ValueError("Production order not found")
    if p_order.status == "COMPLETED":
        raise ValueError("Production order is already completed")

    recipe = p_order.recipe
    target_units = Decimal(str(p_order.target_quantity))
    if target_units <= 0:
        raise ValueError("Target production quantity must be greater than zero")

    multiplier = target_units / Decimal(str(recipe.yield_quantity or 1))

    # Accounts map for BOM components
    roasted_acc = db.query(Account).filter(Account.code == "1320").first()
    spices_acc = db.query(Account).filter(Account.code == "1330").first()
    pkg_acc = db.query(Account).filter(Account.code == "1340").first()
    fg_acc = db.query(Account).filter(Account.code == "1350").first()

    component_credits = {
        "ROASTED": Decimal('0.00'),
        "SPICE": Decimal('0.00'),
        "PACKAGING": Decimal('0.00')
    }

    total_batch_cost = Decimal('0.00')

    # Default warehouse mappings
    wh_roast = db.query(Warehouse).filter(Warehouse.code == "WH-ROAST").first()
    wh_spice = db.query(Warehouse).filter(Warehouse.code == "WH-SPICE").first()
    wh_pkg = db.query(Warehouse).filter(Warehouse.code == "WH-PKG").first()

    for item_line in recipe.items:
        comp_item = item_line.item
        req_qty = Decimal(str(item_line.quantity)) * multiplier
        unit_cost = Decimal(str(comp_item.cost_price or 0))
        line_cost = (req_qty * unit_cost).quantize(Decimal('0.01'))
        total_batch_cost += line_cost

        # Determine warehouse
        src_wh = None
        if comp_item.category == "ROASTED_COFFEE":
            src_wh = wh_roast
            component_credits["ROASTED"] += line_cost
        elif comp_item.category == "SPICE":
            src_wh = wh_spice
            component_credits["SPICE"] += line_cost
        else:
            src_wh = wh_pkg
            component_credits["PACKAGING"] += line_cost

        # Record stock reduction
        record_stock_movement(
            db=db,
            item_id=comp_item.id,
            from_warehouse_id=src_wh.id if src_wh else None,
            to_warehouse_id=None,
            quantity=req_qty,
            uom_id=item_line.uom_id,
            unit_cost=unit_cost,
            move_type="PACKAGING_INPUT",
            reference=p_order.order_number,
            created_by_id=user_id
        )

    unit_cost_finished = (total_batch_cost / target_units).quantize(Decimal('0.0001'))
    p_order.total_cost = total_batch_cost
    p_order.unit_cost = unit_cost_finished
    p_order.status = "COMPLETED"
    p_order.completed_at = datetime.utcnow()

    # Add finished item to Finished Goods warehouse
    fg_item = recipe.finished_item
    record_stock_movement(
        db=db,
        item_id=fg_item.id,
        from_warehouse_id=None,
        to_warehouse_id=p_order.destination_warehouse_id,
        quantity=target_units,
        uom_id=fg_item.uom_id,
        unit_cost=unit_cost_finished,
        move_type="PACKAGING_OUTPUT",
        reference=p_order.order_number,
        created_by_id=user_id
    )

    update_item_weighted_cost(db, fg_item, target_units, unit_cost_finished)

    # Post Automated Double-Entry Journal Entry
    journal_lines = [
        {
            "account_id": fg_acc.id,
            "debit": total_batch_cost,
            "credit": Decimal('0.00'),
            "description": f"Production Order {p_order.order_number}: {target_units} units of {fg_item.name}"
        }
    ]

    if component_credits["ROASTED"] > Decimal('0.00'):
        journal_lines.append({
            "account_id": roasted_acc.id,
            "debit": Decimal('0.00'),
            "credit": component_credits["ROASTED"],
            "description": f"Production {p_order.order_number}: Roasted coffee consumed"
        })
    if component_credits["SPICE"] > Decimal('0.00'):
        journal_lines.append({
            "account_id": spices_acc.id,
            "debit": Decimal('0.00'),
            "credit": component_credits["SPICE"],
            "description": f"Production {p_order.order_number}: Additives & Spices consumed"
        })
    if component_credits["PACKAGING"] > Decimal('0.00'):
        journal_lines.append({
            "account_id": pkg_acc.id,
            "debit": Decimal('0.00'),
            "credit": component_credits["PACKAGING"],
            "description": f"Production {p_order.order_number}: Packaging materials consumed"
        })

    # Balance check safeguard: if any tiny rounding discrepancy occurs, assign to first credit line
    sum_debit = sum([l['debit'] for l in journal_lines])
    sum_credit = sum([l['credit'] for l in journal_lines])
    diff = sum_debit - sum_credit
    if diff != Decimal('0.00') and len(journal_lines) > 1:
        journal_lines[1]['credit'] += diff

    journal_entry = create_balanced_journal_entry(
        db=db,
        entry_date=p_order.date,
        reference=p_order.order_number,
        source_document="PACKAGING",
        source_id=p_order.id,
        narration=f"BOM Blending & Packaging Order {p_order.order_number} - Output {target_units} packages",
        lines=journal_lines,
        created_by_id=user_id
    )
    p_order.journal_entry_id = journal_entry.id

    db.flush()
    return p_order
