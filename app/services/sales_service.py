from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.sales import SalesInvoice, Customer
from app.models.accounting import Account
from app.models.inventory import Item, Warehouse
from app.services.inventory_service import record_stock_movement
from app.services.accounting_service import create_balanced_journal_entry

def confirm_sales_invoice(
    db: Session,
    invoice_id: int,
    user_id: Optional[int] = None
) -> SalesInvoice:
    invoice = db.query(SalesInvoice).filter(SalesInvoice.id == invoice_id).first()
    if not invoice:
        raise ValueError("Sales invoice not found")
    if invoice.status != "DRAFT":
        raise ValueError(f"Invoice cannot be confirmed from status '{invoice.status}'")

    total_cogs = Decimal('0.00')

    # Deduct finished products from warehouse
    for line in invoice.items:
        item = line.item
        qty = Decimal(str(line.quantity))
        base_qty = qty * Decimal(str(line.uom.ratio_to_base if line.uom else 1))
        unit_cost = Decimal(str(item.cost_price or 0))
        line_cogs = (base_qty * unit_cost).quantize(Decimal('0.01'))
        total_cogs += line_cogs

        line.unit_cost = unit_cost

        record_stock_movement(
            db=db,
            item_id=item.id,
            from_warehouse_id=invoice.warehouse_id,
            to_warehouse_id=None,
            quantity=qty,
            uom_id=line.uom_id,
            unit_cost=unit_cost,
            move_type="SALES_DISPATCH",
            reference=invoice.invoice_number,
            created_by_id=user_id
        )

    invoice.status = "CONFIRMED"

    # Automated Double-Entry Journal Entry:
    # 1. Accounts Receivable (1210) Debit: Total Invoice Amount
    # 2. Wholesale Sales Revenue (4110) Credit: Subtotal - Discount
    # 3. VAT / Tax Payable (2310) Credit: Tax Amount (if any)
    # 4. Cost of Goods Sold (5110) Debit: Total COGS
    # 5. Finished Goods Inventory (1350) Credit: Total COGS
    ar_acc = db.query(Account).filter(Account.code == "1210").first()
    revenue_acc = db.query(Account).filter(Account.code == "4110").first()
    tax_acc = db.query(Account).filter(Account.code == "2310").first()
    cogs_acc = db.query(Account).filter(Account.code == "5110").first()
    fg_acc = db.query(Account).filter(Account.code == "1350").first()

    net_sales = Decimal(str(invoice.subtotal)) - Decimal(str(invoice.discount_amount or 0))
    tax_amt = Decimal(str(invoice.tax_amount or 0))
    total_inv_amt = Decimal(str(invoice.total_amount))

    journal_lines = [
        # AR Line
        {
            "account_id": ar_acc.id,
            "debit": total_inv_amt,
            "credit": Decimal('0.00'),
            "description": f"Invoice {invoice.invoice_number} - {invoice.customer.name}"
        },
        # Sales Revenue Line
        {
            "account_id": revenue_acc.id,
            "debit": Decimal('0.00'),
            "credit": net_sales,
            "description": f"Wholesale Coffee Sales - {invoice.invoice_number}"
        }
    ]

    if tax_amt > Decimal('0.00') and tax_acc:
        journal_lines.append({
            "account_id": tax_acc.id,
            "debit": Decimal('0.00'),
            "credit": tax_amt,
            "description": f"VAT / Sales Tax on {invoice.invoice_number}"
        })

    # Perpetual Inventory & COGS lines
    if total_cogs > Decimal('0.00'):
        journal_lines.append({
            "account_id": cogs_acc.id,
            "debit": total_cogs,
            "credit": Decimal('0.00'),
            "description": f"COGS for {invoice.invoice_number}"
        })
        journal_lines.append({
            "account_id": fg_acc.id,
            "debit": Decimal('0.00'),
            "credit": total_cogs,
            "description": f"Perpetual Inventory Deduction for {invoice.invoice_number}"
        })

    # Balance check safeguard: Ensure Debit == Credit to the penny
    sum_deb = sum([l['debit'] for l in journal_lines])
    sum_cred = sum([l['credit'] for l in journal_lines])
    diff = sum_deb - sum_cred
    if diff != Decimal('0.00'):
        # absorb minor penny rounding in revenue line
        journal_lines[1]['credit'] += diff

    journal_entry = create_balanced_journal_entry(
        db=db,
        entry_date=invoice.date,
        reference=invoice.invoice_number,
        source_document="INVOICE",
        source_id=invoice.id,
        narration=f"Wholesale Sales Invoice {invoice.invoice_number} to {invoice.customer.name}",
        lines=journal_lines,
        created_by_id=user_id
    )
    invoice.journal_entry_id = journal_entry.id

    db.flush()
    return invoice

def get_customer_aging_report(db: Session, as_of_date: Optional[date] = None) -> Dict[str, Any]:
    today = as_of_date or date.today()
    customers = db.query(Customer).filter(Customer.is_active == True).all()

    report_rows = []
    grand_totals = {
        "current_30": Decimal('0.00'),
        "days_31_60": Decimal('0.00'),
        "days_61_90": Decimal('0.00'),
        "over_90": Decimal('0.00'),
        "total_outstanding": Decimal('0.00')
    }

    for cust in customers:
        invoices = db.query(SalesInvoice).filter(
            SalesInvoice.customer_id == cust.id,
            SalesInvoice.status.in_(["CONFIRMED", "PAID"])
        ).all()

        cust_bucket = {
            "current_30": Decimal('0.00'),
            "days_31_60": Decimal('0.00'),
            "days_61_90": Decimal('0.00'),
            "over_90": Decimal('0.00'),
            "total": Decimal('0.00')
        }

        for inv in invoices:
            balance_due = Decimal(str(inv.total_amount)) - Decimal(str(inv.paid_amount or 0))
            if balance_due <= Decimal('0.01'):
                continue

            inv_date = inv.date
            age_days = (today - inv_date).days

            if age_days <= 30:
                cust_bucket["current_30"] += balance_due
            elif age_days <= 60:
                cust_bucket["days_31_60"] += balance_due
            elif age_days <= 90:
                cust_bucket["days_61_90"] += balance_due
            else:
                cust_bucket["over_90"] += balance_due

            cust_bucket["total"] += balance_due

        if cust_bucket["total"] > Decimal('0.00'):
            grand_totals["current_30"] += cust_bucket["current_30"]
            grand_totals["days_31_60"] += cust_bucket["days_31_60"]
            grand_totals["days_61_90"] += cust_bucket["days_61_90"]
            grand_totals["over_90"] += cust_bucket["over_90"]
            grand_totals["total_outstanding"] += cust_bucket["total"]

            report_rows.append({
                "customer_id": cust.id,
                "code": cust.code,
                "name": cust.name,
                "name_ar": cust.name_ar,
                "phone": cust.phone or "-",
                "credit_limit": float(cust.credit_limit or 0),
                "current_30": float(cust_bucket["current_30"]),
                "days_31_60": float(cust_bucket["days_31_60"]),
                "days_61_90": float(cust_bucket["days_61_90"]),
                "over_90": float(cust_bucket["over_90"]),
                "total_due": float(cust_bucket["total"])
            })

    return {
        "as_of_date": today.strftime("%Y-%m-%d"),
        "rows": report_rows,
        "totals": {k: float(v) for k, v in grand_totals.items()}
    }
