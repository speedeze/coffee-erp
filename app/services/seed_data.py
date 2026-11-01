from decimal import Decimal
from datetime import date
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.accounting import Account
from app.models.inventory import UnitOfMeasure, Warehouse, Item, StockQuant
from app.models.manufacturing import Recipe, RecipeItem
from app.models.purchase import Supplier
from app.models.sales import Customer
from app.models.treasury import TreasuryAccount
from app.auth import hash_password

def seed_initial_data(db: Session):
    # 1. Seed 4 Accountants
    if db.query(User).count() == 0:
        accountants = [
            User(
                username="admin",
                full_name="Chief Accountant & System Auditor",
                full_name_ar="أحمد الشريف - رئيس الحسابات ومدير النظام",
                email="chief@coffeeroast.local",
                hashed_password=hash_password("admin123"),
                role="CHIEF_ACCOUNTANT",
                is_active=True
            ),
            User(
                username="inv_accountant",
                full_name="Cost & Inventory Accountant",
                full_name_ar="خالد محمود - محاسب التكاليف والمخازن",
                email="inventory@coffeeroast.local",
                hashed_password=hash_password("inv123"),
                role="INVENTORY_ACCOUNTANT",
                is_active=True
            ),
            User(
                username="purch_accountant",
                full_name="Purchases & Foreign Accounts",
                full_name_ar="طارق فهمي - محاسب المشتريات والموردين",
                email="purchases@coffeeroast.local",
                hashed_password=hash_password("purch123"),
                role="PURCHASES_ACCOUNTANT",
                is_active=True
            ),
            User(
                username="sales_accountant",
                full_name="Sales & Receivables Accountant",
                full_name_ar="منى عبد الله - محاسب المبيعات والعملاء",
                email="sales@coffeeroast.local",
                hashed_password=hash_password("sales123"),
                role="SALES_ACCOUNTANT",
                is_active=True
            )
        ]
        db.add_all(accountants)
        db.flush()

    # 2. Seed Chart of Accounts
    if db.query(Account).count() == 0:
        accounts = [
            # ASSETS
            Account(code="1000", name="Assets", name_ar="الأصول", type="ASSET", category="TOP"),
            Account(code="1100", name="Cash & Bank Balances", name_ar="النقدية وما في حكمها", type="ASSET", category="CURRENT_ASSET"),
            Account(code="1110", name="Main Treasury Cash Drawer", name_ar="الخزينة الرئيسية", type="ASSET", category="CURRENT_ASSET"),
            Account(code="1120", name="Local Bank Current Account", name_ar="الحساب الجاري بالبنك المحلي", type="ASSET", category="CURRENT_ASSET"),
            Account(code="1130", name="USD Import Bank Account", name_ar="حساب البنك بالدولار للاستيراد", type="ASSET", category="CURRENT_ASSET"),
            Account(code="1200", name="Receivables", name_ar="المدينون والعملاء", type="ASSET", category="RECEIVABLE"),
            Account(code="1210", name="Trade Accounts Receivable", name_ar="حسابات العملاء التجاريين", type="ASSET", category="RECEIVABLE"),
            Account(code="1300", name="Inventories", name_ar="المخزون السلعي", type="ASSET", category="INVENTORY"),
            Account(code="1310", name="Raw Green Coffee Inventory", name_ar="مخزون البن الأخضر الخام", type="ASSET", category="INVENTORY"),
            Account(code="1320", name="Roasted & Ground Coffee Inventory", name_ar="مخزون البن المحمص والمطحون", type="ASSET", category="INVENTORY"),
            Account(code="1330", name="Additives & Spices Inventory", name_ar="مخزون الإضافات والبهارات", type="ASSET", category="INVENTORY"),
            Account(code="1340", name="Packaging Materials Inventory", name_ar="مخزون مواد التعبئة والتغليف", type="ASSET", category="INVENTORY"),
            Account(code="1350", name="Finished Goods Inventory", name_ar="مخزون المنتجات تامة الصنع", type="ASSET", category="INVENTORY"),
            Account(code="1400", name="Fixed Assets", name_ar="الأصول الثابتة", type="ASSET", category="NON_CURRENT_ASSET"),
            Account(code="1410", name="Roasting Machinery & Equipment", name_ar="ماكينات ومحامص البن الصناعية", type="ASSET", category="NON_CURRENT_ASSET"),
            
            # LIABILITIES
            Account(code="2000", name="Liabilities", name_ar="الالتزامات", type="LIABILITY", category="TOP"),
            Account(code="2100", name="Current Liabilities", name_ar="الالتزامات المتداولة", type="LIABILITY", category="CURRENT_LIABILITY"),
            Account(code="2110", name="Trade Accounts Payable", name_ar="الموردين وحسابات الدائنين", type="LIABILITY", category="PAYABLE"),
            Account(code="2120", name="Accrued Landed Costs & Customs", name_ar="جمارك ومصاريف شحن مستحقة", type="LIABILITY", category="CURRENT_LIABILITY"),
            Account(code="2130", name="Accrued Roasting Overhead & Utilities", name_ar="مصروفات تشغيل ومنافع مستحقة", type="LIABILITY", category="CURRENT_LIABILITY"),
            Account(code="2310", name="Value Added Tax (VAT) Payable", name_ar="ضريبة القيمة المضافة المستحقة", type="LIABILITY", category="CURRENT_LIABILITY"),

            # EQUITY
            Account(code="3000", name="Equity", name_ar="حقوق الملكية", type="EQUITY", category="TOP"),
            Account(code="3100", name="Paid-in Capital", name_ar="رأس المال المدفوع", type="EQUITY", category="EQUITY"),
            Account(code="3200", name="Retained Earnings", name_ar="الأرباح المحتجزة", type="EQUITY", category="EQUITY"),

            # REVENUES
            Account(code="4000", name="Revenues", name_ar="الإيرادات", type="REVENUE", category="TOP"),
            Account(code="4110", name="Wholesale Coffee Sales Revenue", name_ar="إيرادات مبيعات البن بالجملة", type="REVENUE", category="TRADING_REVENUE"),
            Account(code="4120", name="By-Product & Chaff Sales", name_ar="إيرادات بيع مخلفات وقشور التحميص", type="REVENUE", category="TRADING_REVENUE"),

            # EXPENSES
            Account(code="5000", name="Expenses", name_ar="المصروفات", type="EXPENSE", category="TOP"),
            Account(code="5110", name="Cost of Goods Sold (COGS)", name_ar="تكلفة البضاعة المباعة", type="EXPENSE", category="COGS"),
            Account(code="5210", name="Roasting Shrinkage & Loss Variance", name_ar="فروقات وهالك التحميص غير العادي", type="EXPENSE", category="EXPENSE"),
            Account(code="5220", name="Direct Roasting Gas & Energy", name_ar="طاقة وغاز المحامص الصناعية", type="EXPENSE", category="EXPENSE"),
            Account(code="5310", name="Warehouse Handling & Logistics", name_ar="مصاريف مناولة المستودعات", type="EXPENSE", category="EXPENSE"),
            Account(code="5410", name="Administrative & Operating Expenses", name_ar="مصروفات إدارية وعمومية", type="EXPENSE", category="EXPENSE")
        ]
        db.add_all(accounts)
        db.flush()

    # 3. Seed Units of Measure
    if db.query(UnitOfMeasure).count() == 0:
        uoms = [
            UnitOfMeasure(code="KG", name="Kilogram", name_ar="كيلوجرام", category="WEIGHT", ratio_to_base=Decimal('1.0000')),
            UnitOfMeasure(code="G", name="Gram", name_ar="جرام", category="WEIGHT", ratio_to_base=Decimal('0.0010')),
            UnitOfMeasure(code="TON", name="Metric Ton", name_ar="طن متري", category="WEIGHT", ratio_to_base=Decimal('1000.0000')),
            UnitOfMeasure(code="BAG60", name="Jute Bag 60kg", name_ar="شوال خيش 60 كجم", category="WEIGHT", ratio_to_base=Decimal('60.0000')),
            UnitOfMeasure(code="PCS", name="Piece / Pouch", name_ar="حبة / كيس", category="UNIT", ratio_to_base=Decimal('1.0000'))
        ]
        db.add_all(uoms)
        db.flush()

    # 4. Seed 5 Dedicated Warehouses
    if db.query(Warehouse).count() == 0:
        acc_1310 = db.query(Account).filter(Account.code == "1310").first()
        acc_1320 = db.query(Account).filter(Account.code == "1320").first()
        acc_1330 = db.query(Account).filter(Account.code == "1330").first()
        acc_1340 = db.query(Account).filter(Account.code == "1340").first()
        acc_1350 = db.query(Account).filter(Account.code == "1350").first()

        warehouses = [
            Warehouse(code="WH-RAW", name="Raw Coffee Warehouse", name_ar="مستودع البن الأخضر الخام", account_id=acc_1310.id if acc_1310 else None),
            Warehouse(code="WH-ROAST", name="Roasted & Ground Coffee Warehouse", name_ar="مستودع البن المحمص والمطحون", account_id=acc_1320.id if acc_1320 else None),
            Warehouse(code="WH-SPICE", name="Additives & Spices Warehouse", name_ar="مستودع الإضافات والبهارات", account_id=acc_1330.id if acc_1330 else None),
            Warehouse(code="WH-PKG", name="Packaging Materials Warehouse", name_ar="مستودع مواد التعبئة والتغليف", account_id=acc_1340.id if acc_1340 else None),
            Warehouse(code="WH-FG", name="Finished Goods Warehouse", name_ar="مستودع المنتجات تامة الصنع", account_id=acc_1350.id if acc_1350 else None)
        ]
        db.add_all(warehouses)
        db.flush()

    # 5. Seed Items Catalog
    if db.query(Item).count() == 0:
        kg_uom = db.query(UnitOfMeasure).filter(UnitOfMeasure.code == "KG").first()
        pcs_uom = db.query(UnitOfMeasure).filter(UnitOfMeasure.code == "PCS").first()

        raw_wh = db.query(Warehouse).filter(Warehouse.code == "WH-RAW").first()
        roast_wh = db.query(Warehouse).filter(Warehouse.code == "WH-ROAST").first()
        spice_wh = db.query(Warehouse).filter(Warehouse.code == "WH-SPICE").first()
        pkg_wh = db.query(Warehouse).filter(Warehouse.code == "WH-PKG").first()
        fg_wh = db.query(Warehouse).filter(Warehouse.code == "WH-FG").first()

        items = [
            # Raw Beans
            Item(sku="RAW-BRA-01", name="Brazilian Santos NY 2/3 (Green)", name_ar="بن برازيلي سانتوس أخضر", category="RAW_COFFEE", uom_id=kg_uom.id, cost_price=Decimal('6.5000'), selling_price=Decimal('0.00'), reorder_level=Decimal('500.00')),
            Item(sku="RAW-COL-01", name="Colombian Supremo (Green)", name_ar="بن كولومبي سوبريمو أخضر", category="RAW_COFFEE", uom_id=kg_uom.id, cost_price=Decimal('8.2000'), selling_price=Decimal('0.00'), reorder_level=Decimal('300.00')),
            Item(sku="RAW-ETH-01", name="Ethiopian Yirgacheffe G2 (Green)", name_ar="بن إثيوبي يرغاتشيفي أخضر", category="RAW_COFFEE", uom_id=kg_uom.id, cost_price=Decimal('9.5000'), selling_price=Decimal('0.00'), reorder_level=Decimal('200.00')),
            Item(sku="RAW-VNM-01", name="Vietnam Robusta Grade 1 (Green)", name_ar="بن روبوستا فيتنامي أخضر", category="RAW_COFFEE", uom_id=kg_uom.id, cost_price=Decimal('4.2000'), selling_price=Decimal('0.00'), reorder_level=Decimal('600.00')),
            
            # Roasted Coffee
            Item(sku="ROAST-BRA-MED", name="Roasted Brazilian Santos (Medium)", name_ar="بن برازيلي محمص ومطحون وسط", category="ROASTED_COFFEE", uom_id=kg_uom.id, cost_price=Decimal('7.9268'), selling_price=Decimal('0.00')),
            Item(sku="ROAST-COL-MED", name="Roasted Colombian Supremo (Medium)", name_ar="بن كولومبي محمص ومطحون وسط", category="ROASTED_COFFEE", uom_id=kg_uom.id, cost_price=Decimal('10.0000'), selling_price=Decimal('0.00')),
            Item(sku="ROAST-VNM-DRK", name="Roasted Vietnam Robusta (Dark)", name_ar="بن روبوستا فيتنامي محمص غامق", category="ROASTED_COFFEE", uom_id=kg_uom.id, cost_price=Decimal('5.2500'), selling_price=Decimal('0.00')),

            # Spices / Additives
            Item(sku="SPC-CARD-01", name="Green Cardamom Grade 1", name_ar="حبهان / هيل أخضر نمرة 1", category="SPICE", uom_id=kg_uom.id, cost_price=Decimal('28.0000'), selling_price=Decimal('0.00')),
            Item(sku="SPC-MAST-01", name="Greek Chios Mastic", name_ar="مستكة يوناني فاخرة", category="SPICE", uom_id=kg_uom.id, cost_price=Decimal('95.0000'), selling_price=Decimal('0.00')),

            # Packaging
            Item(sku="PKG-BAG-250G", name="Degassing Valve Foil Pouch 250g", name_ar="كيس ألومنيوم صمام 250جم", category="PACKAGING", uom_id=pcs_uom.id, cost_price=Decimal('0.3500'), selling_price=Decimal('0.00')),
            Item(sku="PKG-BAG-1KG", name="Degassing Valve Foil Pouch 1kg", name_ar="كيس ألومنيوم صمام 1كجم", category="PACKAGING", uom_id=pcs_uom.id, cost_price=Decimal('0.6500'), selling_price=Decimal('0.00')),
            Item(sku="PKG-LBL-GOLD", name="Gold Foil Blend Label Sticker", name_ar="استيكر لاصق ذهبي فاخر", category="PACKAGING", uom_id=pcs_uom.id, cost_price=Decimal('0.0800'), selling_price=Decimal('0.00')),

            # Finished Goods
            Item(sku="FG-ARB-CARD-250", name="Premium Arabic Blend with Cardamom 250g", name_ar="قهوة عربي فاخرة بالهيل 250 جم", category="FINISHED_GOODS", uom_id=pcs_uom.id, cost_price=Decimal('2.8500'), selling_price=Decimal('5.5000')),
            Item(sku="FG-ESPR-BLEND-1KG", name="Italian Dark Espresso Blend 1kg", name_ar="اسبريسو بلند إيطالي 1 كجم", category="FINISHED_GOODS", uom_id=pcs_uom.id, cost_price=Decimal('7.8000'), selling_price=Decimal('14.0000'))
        ]
        db.add_all(items)
        db.flush()

        # Seed initial stock levels in respective warehouses
        initial_stocks = [
            (items[0], raw_wh, Decimal('3600.0000')),    # 3,600 kg Brazilian Green
            (items[1], raw_wh, Decimal('2400.0000')),    # 2,400 kg Colombian Green
            (items[2], raw_wh, Decimal('1200.0000')),    # 1,200 kg Ethiopian Green
            (items[3], raw_wh, Decimal('4500.0000')),    # 4,500 kg Vietnam Green
            (items[4], roast_wh, Decimal('450.0000')),   # 450 kg Roasted Brazilian
            (items[5], roast_wh, Decimal('250.0000')),   # 250 kg Roasted Colombian
            (items[6], roast_wh, Decimal('600.0000')),   # 600 kg Roasted Vietnam
            (items[7], spice_wh, Decimal('85.0000')),    # 85 kg Cardamom
            (items[8], spice_wh, Decimal('15.0000')),    # 15 kg Mastic
            (items[9], pkg_wh, Decimal('5000.0000')),    # 5,000 Bags 250g
            (items[10], pkg_wh, Decimal('3000.0000')),   # 3,000 Bags 1kg
            (items[11], pkg_wh, Decimal('10000.0000')),  # 10,000 Labels
            (items[12], fg_wh, Decimal('850.0000')),     # 850 units Arabic Blend 250g
            (items[13], fg_wh, Decimal('420.0000')),     # 420 units Espresso Blend 1kg
        ]

        for itm, wh, qty in initial_stocks:
            quant = StockQuant(item_id=itm.id, warehouse_id=wh.id, quantity=qty)
            db.add(quant)
        db.flush()

    # 6. Seed Recipes (BOMs)
    if db.query(Recipe).count() == 0:
        kg_uom = db.query(UnitOfMeasure).filter(UnitOfMeasure.code == "KG").first()
        pcs_uom = db.query(UnitOfMeasure).filter(UnitOfMeasure.code == "PCS").first()

        fg_arabic = db.query(Item).filter(Item.sku == "FG-ARB-CARD-250").first()
        fg_espresso = db.query(Item).filter(Item.sku == "FG-ESPR-BLEND-1KG").first()
        roast_bra = db.query(Item).filter(Item.sku == "ROAST-BRA-MED").first()
        roast_vnm = db.query(Item).filter(Item.sku == "ROAST-VNM-DRK").first()
        cardamom = db.query(Item).filter(Item.sku == "SPC-CARD-01").first()
        pouch_250 = db.query(Item).filter(Item.sku == "PKG-BAG-250G").first()
        pouch_1kg = db.query(Item).filter(Item.sku == "PKG-BAG-1KG").first()
        label_gold = db.query(Item).filter(Item.sku == "PKG-LBL-GOLD").first()

        recipe1 = Recipe(
            code="BOM-ARABIC-250G",
            name="Premium Arabic Blend with Cardamom 250g",
            name_ar="تركيبة القهوة العربي الفاخرة بالهيل 250جم",
            finished_item_id=fg_arabic.id,
            yield_quantity=Decimal('1.0000'),
            yield_uom_id=pcs_uom.id,
            description="Blend of 230g medium roasted Brazilian beans + 20g ground green cardamom in 250g foil pouch"
        )
        db.add(recipe1)
        db.flush()

        recipe1_items = [
            RecipeItem(recipe_id=recipe1.id, item_id=roast_bra.id, quantity=Decimal('0.2300'), uom_id=kg_uom.id, notes="Medium roast ground"),
            RecipeItem(recipe_id=recipe1.id, item_id=cardamom.id, quantity=Decimal('0.0200'), uom_id=kg_uom.id, notes="Fine ground green cardamom"),
            RecipeItem(recipe_id=recipe1.id, item_id=pouch_250.id, quantity=Decimal('1.0000'), uom_id=pcs_uom.id, notes="Foil pouch with valve"),
            RecipeItem(recipe_id=recipe1.id, item_id=label_gold.id, quantity=Decimal('1.0000'), uom_id=pcs_uom.id, notes="Gold blend sticker")
        ]
        db.add_all(recipe1_items)

        recipe2 = Recipe(
            code="BOM-ESPRESSO-1KG",
            name="Italian Dark Espresso Blend 1kg",
            name_ar="تركيبة الاسبريسو الإيطالي الغامق 1كجم",
            finished_item_id=fg_espresso.id,
            yield_quantity=Decimal('1.0000'),
            yield_uom_id=pcs_uom.id,
            description="70% Brazilian Santos Medium + 30% Vietnam Robusta Dark in 1kg valve bag"
        )
        db.add(recipe2)
        db.flush()

        recipe2_items = [
            RecipeItem(recipe_id=recipe2.id, item_id=roast_bra.id, quantity=Decimal('0.7000'), uom_id=kg_uom.id, notes="Arabica base 70%"),
            RecipeItem(recipe_id=recipe2.id, item_id=roast_vnm.id, quantity=Decimal('0.3000'), uom_id=kg_uom.id, notes="Robusta crema booster 30%"),
            RecipeItem(recipe_id=recipe2.id, item_id=pouch_1kg.id, quantity=Decimal('1.0000'), uom_id=pcs_uom.id, notes="1kg valve bag")
        ]
        db.add_all(recipe2_items)
        db.flush()

    # 7. Seed Suppliers
    if db.query(Supplier).count() == 0:
        suppliers = [
            Supplier(
                code="SUP-BRA-01",
                name="Santos Green Bean Exporters S.A.",
                name_ar="شركة مصدرين بن سانتوس البرازيلية",
                country="Brazil",
                is_foreign=True,
                currency="USD",
                phone="+55 13 3219-4400",
                email="export@santoscoffee.br",
                address="Rua do Comercio, Santos, SP, Brazil"
            ),
            Supplier(
                code="SUP-COL-01",
                name="Bogota Specialty Coffee Trading",
                name_ar="شركة تجارة القهوة المختصة ببوغوتا",
                country="Colombia",
                is_foreign=True,
                currency="USD",
                phone="+57 1 742-8800",
                email="contact@bogotacoffee.co",
                address="Carrera 7 # 71-21, Bogota, Colombia"
            ),
            Supplier(
                code="SUP-LOC-01",
                name="Al-Barakah Spice & Cardamom Imports",
                name_ar="مؤسسة البركة لاستيراد الهيل والبهارات",
                country="Local",
                is_foreign=False,
                currency="EGP",
                phone="+20 2 2590-1122",
                email="albarakah@spices.eg",
                address="15 Al-Mu'izz Street, Cairo"
            ),
            Supplier(
                code="SUP-PKG-01",
                name="Modern PolyPack Industries",
                name_ar="شركة بوليباك لمواد التعبئة والتغليف",
                country="Local",
                is_foreign=False,
                currency="EGP",
                phone="+20 2 3833-9911",
                email="sales@polypack.eg",
                address="6th of October Industrial Zone 3"
            )
        ]
        db.add_all(suppliers)
        db.flush()

    # 8. Seed Wholesale Customers
    if db.query(Customer).count() == 0:
        customers = [
            Customer(
                code="CUST-001",
                name="Royal Coffee House Chain (15 Branches)",
                name_ar="سلسلة مقاهي البيت الملكي (15 فرع)",
                customer_type="CAFE",
                phone="+20 100 4455-889",
                email="procurement@royalcoffee.eg",
                credit_limit=Decimal('50000.00'),
                credit_period_days=30
            ),
            Customer(
                code="CUST-002",
                name="Grand Gourmet Wholesale Supermarkets",
                name_ar="مجموعة أسواق جراند جورميه للجملة",
                customer_type="WHOLESALER",
                phone="+20 102 8899-771",
                email="orders@grandgourmet.eg",
                credit_limit=Decimal('100000.00'),
                credit_period_days=45
            ),
            Customer(
                code="CUST-003",
                name="Nile Plaza Luxury Hotel & Resorts",
                name_ar="فندق ومنتجع نايل بلازا الفاخر",
                customer_type="HOTEL",
                phone="+20 2 2795-7100",
                email="fnb@nileplazahotel.eg",
                credit_limit=Decimal('40000.00'),
                credit_period_days=30
            )
        ]
        db.add_all(customers)
        db.flush()

    # 9. Seed Treasury Accounts
    if db.query(TreasuryAccount).count() == 0:
        acc_1110 = db.query(Account).filter(Account.code == "1110").first()
        acc_1120 = db.query(Account).filter(Account.code == "1120").first()
        acc_1130 = db.query(Account).filter(Account.code == "1130").first()

        treasuries = [
            TreasuryAccount(code="TR-CASH-01", name="Main Cash Drawer", name_ar="الخزينة النقدية الرئيسية", type="CASH", currency="EGP", account_id=acc_1110.id),
            TreasuryAccount(code="TR-BANK-LOC", name="National Commercial Bank (EGP)", name_ar="البنك التجاري المحلي (حساب جاري)", type="BANK", currency="EGP", account_id=acc_1120.id),
            TreasuryAccount(code="TR-BANK-USD", name="International Import Bank (USD)", name_ar="البنك الدولي - حساب استيراد بالدولار", type="BANK", currency="USD", account_id=acc_1130.id)
        ]
        db.add_all(treasuries)
        db.flush()

    db.commit()
