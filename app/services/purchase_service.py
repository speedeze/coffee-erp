from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.models.purchase import PurchaseOrder, Supplier, LandedCost
from app.models.accounting import Account
from app.models.inventory import Item, Warehouse
from app.services.inventory_service import record_stock_movement, update_item_weighted_cost
from app.services.accounting_service import create_balanced_journal_entry

def allocate_order_landed_costs(order: PurchaseOrder):
    """
    Distributes total landed costs across purchase order items proportionally
    based on weight or FOB value.
    """
    total_landed = sum([Decimal(str(lc.amount or 0)) for lc in order.landed_costs])
    order.total_landed_costs = total_landed
    total_fob = sum([Decimal(str(item.subtotal or 0)) for item in order.items])
    order.subtotal_fob = total_fob
    order.grand_total = total_fob + total_landed

    if not order.items:
        return

    # Check preferred allocation method from landed costs, default to weight
    total_weight = sum([
        Decimal(str(i.quantity)) * Decimal(str(i.uom.ratio_to_base if i.uom else 1))
        for i in order.items
    ])

    allocated_so_far = Decimal('0.00')
    items_count = len(order.items)

    for idx, item in enumerate(order.items):
        item_weight = Decimal(str(item.quantity)) * Decimal(str(item.uom.ratio_to_base if item.uom else 1))
        
        if total_weight > Decimal('0.00'):
            share = (item_weight / total_weight) * total_landed
        elif total_fob > Decimal('0.00'):
            share = (Decimal(str(item.subtotal)) / total_fob) * total_landed
        else:
            share = total_landed / Decimal(str(items_count))

        share = share.quantize(Decimal('0.01'))
        # Adjust last item for exact penny match
        if idx == items_count - 1:
            share = total_landed - allocated_so_far
        else:
            allocated_so_far += share

        item.allocated_landed_cost = share
        total_item_landed_cost = Decimal(str(item.subtotal)) + share
        qty = Decimal(str(item.quantity))
        item.effective_unit_cost = (total_item_landed_cost / qty).quantize(Decimal('0.0001')) if qty > 0 else Decimal('0.0000')

def receive_purchase_shipment(
    db: Session,
    order_id: int,
    user_id: Optional[int] = None
) -> PurchaseOrder:
    order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
    if not order:
        raise ValueError("Purchase order not found")
    if order.status == "RECEIVED":
        raise ValueError("Purchase order has already been received")

    # Allocate landed costs
    allocate_order_landed_costs(order)
    order.status = "RECEIVED"
    order.received_at = datetime.utcnow()

    # Move stock into warehouse and update weighted average costs
    for item_line in order.items:
        item = item_line.item
        qty = Decimal(str(item_line.quantity))
        effective_cost = Decimal(str(item_line.effective_unit_cost))
        base_qty = qty * Decimal(str(item_line.uom.ratio_to_base if item_line.uom else 1))
        base_unit_cost = (Decimal(str(item_line.subtotal)) + Decimal(str(item_line.allocated_landed_cost))) / base_qty

        record_stock_movement(
            db=db,
            item_id=item.id,
            from_warehouse_id=None,
            to_warehouse_id=order.warehouse_id,
            quantity=qty,
            uom_id=item_line.uom_id,
            unit_cost=base_unit_cost,
            move_type="PURCHASE_RECEIPT",
            reference=f"{order.order_number} B/L:{order.bill_of_lading or '-'}",
            created_by_id=user_id
        )

        update_item_weighted_cost(db, item, base_qty, base_unit_cost)

    # Automated Double-Entry Journal Entry:
    # Debit: Inventory Asset (1310 Raw Coffee / 1340 Packaging / etc.) for Grand Total
    # Credit: Accounts Payable (2110) for Subtotal FOB
    # Credit: Accrued Customs & Freight (2120) for Total Landed Costs
    dest_wh = order.warehouse
    inv_account = dest_wh.account if (dest_wh and dest_wh.account) else db.query(Account).filter(Account.code == "1310").first()
    ap_account = db.query(Account).filter(Account.code == "2110").first()
    landed_clearing_acc = db.query(Account).filter(Account.code == "2120").first()

    journal_lines = [
        {
            "account_id": inv_account.id,
            "debit": order.grand_total,
            "credit": Decimal('0.00'),
            "description": f"Receipt of shipment {order.order_number} (FOB + Landed Costs)"
        },
        {
            "account_id": ap_account.id,
            "debit": Decimal('0.00'),
            "credit": order.subtotal_fob,
            "description": f"Payable to {order.supplier.name} for {order.order_number}"
        }
    ]

    if order.total_landed_costs > Decimal('0.00'):
        journal_lines.append({
            "account_id": landed_clearing_acc.id,
            "debit": Decimal('0.00'),
            "credit": order.total_landed_costs,
            "description": f"Accrued Customs, Freight & Port charges for {order.order_number}"
        })

    journal_entry = create_balanced_journal_entry(
        db=db,
        entry_date=order.date,
        reference=order.order_number,
        source_document="PURCHASE",
        source_id=order.id,
        narration=f"Import Shipment Receipt {order.order_number} - B/L {order.bill_of_lading or '-'} from {order.supplier.name}",
        lines=journal_lines,
        created_by_id=user_id
    )
    order.journal_entry_id = journal_entry.id

    db.flush()
    return order
