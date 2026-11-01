# CoffeeRoast ERP Monolith - Production-Ready System for Coffee Trading & Manufacturing

A custom, production-ready, on-premise Monolith ERP system tailored specifically for coffee trading and industrial roasting/manufacturing operations. The system is designed for **4 dedicated accountants** handling paper-based transactions with strict role-based access control (RBAC), multi-unit warehousing, roasting shrinkage calculations, landed cost allocations, and an automated double-entry accounting engine.

---

## ☕ Key Industry Highlights & Business Logic

1. **The Roasting & Shrinkage Engine (Core Module)**:
   - Green coffee beans contain 10%-12% moisture that naturally evaporates during roasting (typically 15% to 20% loss).
   - The engine automatically calculates the exact shrinkage percentage:
     $$\text{Shrinkage \%} = \frac{\text{Raw KG} - \text{Actual Roasted KG}}{\text{Raw KG}} \times 100$$
   - Capitalizes 100% of the raw bean cost (plus optional roasting utilities) onto the resulting roasted coffee:
     $$\text{Revalued Cost per KG} = \frac{\text{Total Raw Cost} + \text{Direct Utilities}}{\text{Actual Roasted Yield KG}}$$
   - Posts balanced double-entry journals moving inventory from `WH-RAW` (1310) to `WH-ROAST` (1320).

2. **Blending & Packaging BOM Recipes**:
   - Bill of Materials (BOM) combining ground roasted coffee, spices/additives (Guatemala Cardamom, Mastic), and packaging materials (degassing valve foil pouches, stickers, master cartons).
   - Deducts components from dedicated warehouses and records finished goods stock in `WH-FG` (1350) while posting balancing journals.

3. **Import Shipments & Landed Costs Allocation**:
   - Manages foreign coffee suppliers (Brazil Santos, Colombia Supremo, Ethiopia Yirgacheffe, Vietnam Robusta).
   - Landed costs allocation engine distributes ocean freight, customs tariffs, port demurrage, clearance, and inland transport across coffee lots proportionally by weight or FOB value.

4. **Wholesale Sales Invoicing & Receivables Aging**:
   - Invoicing for cafe chains, supermarkets, and wholesale distributors.
   - Confirmation triggers dual accounting:
     - Revenue Entry: Debit Accounts Receivable (1210), Credit Wholesale Coffee Sales (4110), Credit Tax Payable (2310).
     - COGS Perpetual Entry: Debit Cost of Goods Sold (5110), Credit Finished Goods Inventory (1350).
   - Accounts Receivable Aging Schedule (0-30, 31-60, 61-90, 90+ days).

5. **Double-Entry General Ledger & Financial Statements**:
   - **Trading Account (حساب المتاجرة)**: Debit cost of sales vs Credit sales revenues & closing perpetual inventory to yield Gross Trading Profit.
   - **Income Statement / P&L (قائمة الأرباح والخسائر)**: Revenues - COGS = Gross Profit, less operating/roasting expenses = Net Operating Profit.
   - **Balance Sheet (قائمة المركز المالي)**: Total Assets = Total Liabilities + Owner's Equity.
   - **Trial Balance (ميزان المراجعة)**: Validates total debits == total credits across the Chart of Accounts.

---

## 🏗 System Architecture & Tech Stack

```
coffee_erp_V001/
├── app/
│   ├── config.py                   # Environment settings
│   ├── database.py                 # SQLAlchemy engine, session maker (SQLite & PostgreSQL)
│   ├── auth.py                     # PBKDF2-HMAC-SHA256 hashing, signed sessions, RBAC
│   ├── models/
│   │   ├── user.py                 # User, AuditLog
│   │   ├── accounting.py           # Account, JournalEntry, JournalItem, FinancialPeriod
│   │   ├── inventory.py            # Warehouse, UnitOfMeasure, Item, StockQuant, StockMove
│   │   ├── manufacturing.py        # RoastingOrder, Recipe, RecipeItem, ProductionOrder
│   │   ├── purchase.py             # Supplier, PurchaseOrder, LandedCost
│   │   ├── sales.py                # Customer, SalesInvoice, SalesInvoiceItem
│   │   └── treasury.py             # TreasuryAccount, ReceiptVoucher, PaymentVoucher
│   ├── services/
│   │   ├── accounting_service.py   # Double-entry posting, GL, Trading Account, P&L, Balance Sheet
│   │   ├── inventory_service.py    # Multi-UOM conversions, weighted avg cost (WAC), stock moves
│   │   ├── manufacturing_service.py# Roasting shrinkage math, cost revaluation, BOM production
│   │   ├── purchase_service.py     # Landed cost allocation & shipment receipt
│   │   ├── sales_service.py        # Wholesale invoicing, COGS automation, AR aging
│   │   ├── treasury_service.py     # Receipt (Cash In) & Payment (Cash Out) vouchers
│   │   └── seed_data.py            # Pre-seeded 4 accountants, COA, 5 warehouses, items, recipes
│   ├── routers/                    # FastAPI endpoints & views
│   └── templates/                  # Odoo-inspired UI (Tailwind CSS + Alpine.js + Jinja2)
├── Dockerfile                      # Production Docker container
├── docker-compose.yml              # PostgreSQL 16 + FastAPI containerization
├── requirements.txt
└── .env
```

---

## 👥 The 4 Dedicated Accountants & Default Credentials

The system comes pre-seeded with 4 distinct roles:

| Role | Username | Password | Arabic Title | Primary Responsibilities |
| :--- | :--- | :--- | :--- | :--- |
| **Chief Accountant** | `admin` | `admin123` | رئيس الحسابات والمدير المالي | General Ledger, Chart of Accounts, Period Close, Balance Sheet, Manual Journals |
| **Inventory Accountant** | `inv_accountant` | `inv123` | محاسب التكاليف والمخازن | Roasting Orders, Shrinkage Calculation, BOM Recipes, Packaging Batches, Stock Audit |
| **Purchases Accountant** | `purch_accountant` | `purch123` | محاسب المشتريات والموردين | Import Shipments, Landed Costs (Freight/Customs), Foreign Suppliers, Payment Vouchers |
| **Sales Accountant** | `sales_accountant` | `sales123` | محاسب المبيعات والعملاء | Wholesale Invoicing, Customer Receivables, Aging Reports, Cash Receipt Vouchers |

---

## 🚀 Quick Start & Local Execution

### Option A: Immediate Local Execution (Python)

1. Clone or navigate into the workspace directory:
   ```bash
   cd d:\Projects\coffee_erp_V001
   ```

2. Run the application with Uvicorn:
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. Open your browser and navigate to:
   ```
   http://localhost:8000
   ```

*(On initial startup, SQLite database `coffee_erp.db` is created automatically with full seed data, 5 warehouses, Chart of Accounts, raw coffee beans, spices, packaging materials, and BOM recipes).*

---

### Option B: Production Containerized Deployment (Docker Compose)

To run with containerized PostgreSQL and FastAPI:

```bash
docker compose up -d --build
```

The database container will spin up PostgreSQL 16 with health checks, and the FastAPI container will connect via the internal network at `http://localhost:8000`.

---

## 📊 Five Dedicated Warehouses Architecture

| Warehouse Code | Arabic Name | Category | Linked Asset GL Code |
| :--- | :--- | :--- | :--- |
| **`WH-RAW`** | مستودع البن الأخضر الخام | Raw Green Beans (Brazil, Colombia, Vietnam, Ethiopia) | `#1310` |
| **`WH-ROAST`** | مستودع البن المحمص والمطحون | Roasted Beans (Light, Medium, Dark) | `#1320` |
| **`WH-SPICE`** | مستودع الإضافات والبهارات | Green Cardamom Jumbo, Greek Mastic, Cloves | `#1330` |
| **`WH-PKG`** | مستودع مواد التعبئة والتغليف | Foil Valve Pouches (250g, 1kg), Gold Labels, Cartons | `#1340` |
| **`WH-FG`** | مستودع المنتجات تامة الصنع | Arabic Blend with Cardamom 250g, Espresso Blend 1kg | `#1350` |
