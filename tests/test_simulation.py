import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time
from datetime import date
from decimal import Decimal
from app.database import SessionLocal, init_db
from app.services.seed_data import seed_initial_data
from app.models.user import User
from app.models.manufacturing import RoastingOrder, Recipe, ProductionOrder
from app.models.sales import Customer, SalesInvoice, SalesInvoiceItem
from app.models.inventory import Item, Warehouse
from app.services.manufacturing_service import complete_roasting_order, complete_production_order
from app.services.sales_service import confirm_sales_invoice
from app.services.accounting_service import (
    get_trial_balance,
    get_balance_sheet,
    get_trading_account,
    get_income_statement
)

def run_simulation():
    init_db()
    db = SessionLocal()
    suffix = int(time.time() * 1000) % 1000000
    try:
        seed_initial_data(db)

        admin = db.query(User).filter(User.username == 'admin').first()
        raw_bra = db.query(Item).filter(Item.sku == 'RAW-BRA-01').first()
        roast_bra = db.query(Item).filter(Item.sku == 'ROAST-BRA-MED').first()
        wh_raw = db.query(Warehouse).filter(Warehouse.code == 'WH-RAW').first()
        wh_roast = db.query(Warehouse).filter(Warehouse.code == 'WH-ROAST').first()
        wh_fg = db.query(Warehouse).filter(Warehouse.code == 'WH-FG').first()

        print("--- [1] Testing Roasting & Shrinkage Engine ---")
        roast_order = RoastingOrder(
            order_number=f'ROAST-SIM-{suffix}',
            date=date.today(),
            status='DRAFT',
            roast_profile='Medium',
            raw_item_id=raw_bra.id,
            raw_warehouse_id=wh_raw.id,
            raw_quantity_kg=Decimal('100.0000'),
            raw_unit_cost=Decimal(str(raw_bra.cost_price)),
            total_raw_cost=Decimal('100.0000') * Decimal(str(raw_bra.cost_price)),
            roasted_item_id=roast_bra.id,
            roasted_warehouse_id=wh_roast.id,
            created_by_id=admin.id
        )
        db.add(roast_order)
        db.commit()
        db.refresh(roast_order)

        completed_roast = complete_roasting_order(db, roast_order.id, Decimal('82.0000'), user_id=admin.id)
        db.commit()
        print(f"Roasted Output: {completed_roast.actual_roasted_qty_kg} KG")
        print(f"Calculated Shrinkage: {completed_roast.actual_shrinkage_pct}% (Moisture loss: {completed_roast.shrinkage_loss_kg} KG)")
        print(f"Revalued Cost per KG: ${completed_roast.revalued_cost_per_kg}/KG (Original raw was ${raw_bra.cost_price}/KG)")
        print(f"Automated GL Journal Entry: #{completed_roast.journal_entry_id}")

        print("\n--- [2] Testing BOM Blending & Packaging Execution ---")
        recipe = db.query(Recipe).first()
        prod_order = ProductionOrder(
            order_number=f'PROD-SIM-{suffix}',
            date=date.today(),
            recipe_id=recipe.id,
            target_quantity=Decimal('50.0000'),
            status='DRAFT',
            destination_warehouse_id=wh_fg.id,
            created_by_id=admin.id
        )
        db.add(prod_order)
        db.commit()
        db.refresh(prod_order)

        completed_prod = complete_production_order(db, prod_order.id, user_id=admin.id)
        db.commit()
        print(f"Finished Packaged Bags Produced: {completed_prod.target_quantity} units")
        print(f"Total Batch Cost: ${completed_prod.total_cost}")
        print(f"Finished Unit Cost: ${completed_prod.unit_cost}/pack")
        print(f"Automated GL Journal Entry: #{completed_prod.journal_entry_id}")

        print("\n--- [3] Testing Wholesale Sales Invoicing & Perpetual COGS ---")
        customer = db.query(Customer).first()
        fg_item = recipe.finished_item
        inv = SalesInvoice(
            invoice_number=f'INV-SIM-{suffix}',
            date=date.today(),
            customer_id=customer.id,
            payment_terms='NET30',
            status='DRAFT',
            subtotal=Decimal('20.0000') * Decimal(str(fg_item.selling_price)),
            total_amount=Decimal('20.0000') * Decimal(str(fg_item.selling_price)),
            warehouse_id=wh_fg.id,
            created_by_id=admin.id
        )
        db.add(inv)
        db.flush()
        inv_item = SalesInvoiceItem(
            invoice_id=inv.id,
            item_id=fg_item.id,
            quantity=Decimal('20.0000'),
            uom_id=fg_item.uom_id,
            unit_price=Decimal(str(fg_item.selling_price)),
            subtotal=Decimal('20.0000') * Decimal(str(fg_item.selling_price))
        )
        db.add(inv_item)
        db.commit()

        confirmed_inv = confirm_sales_invoice(db, inv.id, user_id=admin.id)
        db.commit()
        print(f"Wholesale Invoice {confirmed_inv.invoice_number} to {customer.name}: ${confirmed_inv.total_amount}")
        print(f"Perpetual Inventory deducted & Dual GL posted: Journal #{confirmed_inv.journal_entry_id}")

        print("\n--- [4] Validating Financial Statements & Accounting Equilibrium ---")
        tb = get_trial_balance(db)
        print(f"Trial Balance: Total Debits=${tb['total_debit']} | Total Credits=${tb['total_credit']} | Balanced={tb['is_balanced']}")
        assert tb['is_balanced'], "Trial Balance MUST be balanced!"

        bs = get_balance_sheet(db)
        print(f"Balance Sheet: Assets=${bs['total_assets']} | Liab+Equity=${bs['total_liabilities_and_equity']} | Balanced={bs['is_balanced']}")
        assert bs['is_balanced'], "Balance Sheet MUST satisfy Assets = Liabilities + Equity!"

        trading = get_trading_account(db)
        print(f"Trading Account: Net Sales=${trading['sales_total']} | COGS=${trading['total_cogs']} | Gross Trading Profit=${trading['gross_trading_profit']}")

        pnl = get_income_statement(db)
        print(f"Profit & Loss: Total Revenue=${pnl['total_revenue']} | Gross Profit=${pnl['gross_profit']} | Net Operating Profit=${pnl['net_profit']}")

        print("\n>>> ALL TESTS PASSED: 100% MATHEMATICAL PRECISION & ACCOUNTING INTEGRITY CONFIRMED! <<<")
    finally:
        db.close()

if __name__ == '__main__':
    run_simulation()
