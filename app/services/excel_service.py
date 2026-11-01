import io
import csv
from urllib.parse import quote
from decimal import Decimal
from typing import List, Dict, Any, Optional
from datetime import datetime, date
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.models.sales import Customer
from app.models.inventory import Item, Warehouse, UnitOfMeasure, StockQuant
from app.models.purchase import Supplier
from app.services.inventory_service import record_stock_movement

# Styles for Odoo-themed Excel exports
FONT_HEADER = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
FILL_HEADER = PatternFill(start_color="714B67", end_color="714B67", fill_type="solid")  # Odoo Purple
FONT_TITLE = Font(name="Calibri", size=14, bold=True, color="714B67")
FONT_TOTAL = Font(name="Calibri", size=11, bold=True, color="1E293B")
FILL_TOTAL = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
BORDER_THIN = Border(
    left=Side(style="thin", color="E2E8F0"),
    right=Side(style="thin", color="E2E8F0"),
    top=Side(style="thin", color="E2E8F0"),
    bottom=Side(style="thin", color="E2E8F0")
)

def create_excel_streaming_response(
    filename: str,
    sheet_title: str,
    headers: List[str],
    rows: List[List[Any]],
    title: Optional[str] = None
) -> StreamingResponse:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]  # Excel 31 char sheet limit
    ws.sheet_view.rightToLeft = True  # RTL sheet support for Arabic

    current_row = 1
    if title:
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        title_cell = ws.cell(row=1, column=1, value=title)
        title_cell.font = FONT_TITLE
        title_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 30
        current_row = 3

    # Header Row
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=current_row, column=col_idx, value=header)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER_THIN
    ws.row_dimensions[current_row].height = 24

    # Data Rows
    current_row += 1
    for row_data in rows:
        for col_idx, val in enumerate(row_data, 1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.alignment = Alignment(horizontal="right" if isinstance(val, (int, float, Decimal)) else "center", vertical="center")
            cell.border = BORDER_THIN
            if isinstance(val, (int, float, Decimal)):
                cell.number_format = '#,##0.00'
        current_row += 1

    # Auto-adjust column width
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or '')
            if len(val_str) > max_len and cell.row > 1:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    encoded_fn = quote(f"{filename}.xlsx")
    headers_resp = {
        'Content-Disposition': f"attachment; filename=\"export.xlsx\"; filename*=UTF-8''{encoded_fn}",
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    }
    return StreamingResponse(output, headers=headers_resp)

def create_csv_streaming_response(filename: str, headers: List[str], rows: List[List[Any]]) -> StreamingResponse:
    output = io.StringIO()
    # Write UTF-8 BOM so Excel opens Arabic correctly
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    
    mem_stream = io.BytesIO(output.getvalue().encode('utf-8-sig'))
    encoded_fn = quote(f"{filename}.csv")
    headers_resp = {
        'Content-Disposition': f"attachment; filename=\"export.csv\"; filename*=UTF-8''{encoded_fn}",
        'Content-Type': 'text/csv; charset=utf-8'
    }
    return StreamingResponse(mem_stream, headers=headers_resp)

def generate_customers_template() -> StreamingResponse:
    headers = [
        "كود العميل (Code)",
        "اسم العميل بالإنجليزية (Name)",
        "اسم العميل بالعربية (Name AR)",
        "نوع العميل (CAFE/SUPERMARKET/WHOLESALER)",
        "رقم الهاتف (Phone)",
        "البريد الإلكتروني (Email)",
        "الرقم الضريبي (Tax Number)",
        "الحد الائتماني (Credit Limit)",
        "فترة السداد بالأيام (Credit Days)"
    ]
    sample_rows = [
        ["CUST-001", "Al-Masa Cafe", "مقهى الماسة الفاخر", "CAFE", "0501234567", "masa@example.com", "300123456700003", 50000.0, 30],
        ["CUST-002", "Golden Roastery Co", "شركة المحامص الذهبية", "WHOLESALER", "0509876543", "golden@example.com", "300987654300003", 100000.0, 45]
    ]
    return create_excel_streaming_response("نموذج_استيراد_العملاء", "العملاء", headers, sample_rows, "نموذج استيراد العملاء الجديد - CoffeeRoast ERP")

def generate_items_template() -> StreamingResponse:
    headers = [
        "كود الصنف SKU",
        "اسم الصنف بالإنجليزية (Name)",
        "اسم الصنف بالعربية (Name AR)",
        "التصنيف (RAW_COFFEE/ROASTED_COFFEE/SPICE/PACKAGING/FINISHED_GOODS)",
        "كود وحدة القياس (KG/G/TON/BAG60/PCS)",
        "سعر التكلفة (Cost Price)",
        "سعر البيع (Selling Price)",
        "حد إعادة الطلب (Reorder Level)"
    ]
    sample_rows = [
        ["RAW-YEM-01", "Yemen Mokha Matari", "بن يمني مطري فاخر خام", "RAW_COFFEE", "KG", 14.50, 0.0, 100.0],
        ["SPICE-CARD-02", "Indian Cardamom Extra", "هيل هندي حبة كبيرة جامبو", "SPICE", "KG", 28.00, 0.0, 20.0],
        ["PKG-BAG-500", "Valve Foil Bag 500g", "أكياس فويل صمام 500 جرام", "PACKAGING", "PCS", 0.45, 0.0, 500.0]
    ]
    return create_excel_streaming_response("نموذج_استيراد_الأصناف", "الأصناف", headers, sample_rows, "نموذج استيراد دليل الأصناف - CoffeeRoast ERP")

def generate_stock_balances_template() -> StreamingResponse:
    headers = [
        "كود الصنف SKU",
        "كود المستودع (WH-RAW/WH-ROAST/WH-SPICE/WH-PKG/WH-FG)",
        "الكمية الافتتاحية (Quantity)",
        "تكلفة الوحدة (Unit Cost)"
    ]
    sample_rows = [
        ["RAW-BRA-01", "WH-RAW", 500.0, 6.50],
        ["ROAST-BRA-MED", "WH-ROAST", 150.0, 9.20],
        ["FG-ARB-CARD-250", "WH-FG", 200.0, 4.80]
    ]
    return create_excel_streaming_response("نموذج_الأرصدة_الافتتاحية_للمخزون", "الأرصدة الافتتاحية", headers, sample_rows, "نموذج استيراد الأرصدة الافتتاحية للمستودعات")

def import_customers_from_bytes(file_bytes: bytes, filename: str, db: Session, user_id: int) -> Dict[str, Any]:
    rows = []
    if filename.endswith(".csv"):
        text = file_bytes.decode('utf-8-sig', errors='ignore')
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if len(rows) > 0:
            rows = rows[1:]  # skip header
    else:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_row=2, values_only=True):
            if any(row):
                rows.append(list(row))

    imported_count = 0
    updated_count = 0
    errors = []

    for idx, r in enumerate(rows, 2):
        if not r or not r[0]:
            continue
        code = str(r[0]).strip()
        name = str(r[1]).strip() if len(r) > 1 and r[1] else code
        name_ar = str(r[2]).strip() if len(r) > 2 and r[2] else name
        cust_type = str(r[3]).strip().upper() if len(r) > 3 and r[3] else "CAFE"
        phone = str(r[4]).strip() if len(r) > 4 and r[4] else None
        email = str(r[5]).strip() if len(r) > 5 and r[5] else None
        tax_num = str(r[6]).strip() if len(r) > 6 and r[6] else None
        
        try:
            credit_limit = Decimal(str(r[7])) if len(r) > 7 and r[7] is not None else Decimal('0.00')
        except Exception:
            credit_limit = Decimal('0.00')

        try:
            credit_days = int(r[8]) if len(r) > 8 and r[8] is not None else 30
        except Exception:
            credit_days = 30

        existing = db.query(Customer).filter(Customer.code == code).first()
        if existing:
            existing.name = name
            existing.name_ar = name_ar
            existing.customer_type = cust_type
            existing.phone = phone
            existing.email = email
            existing.tax_number = tax_num
            existing.credit_limit = credit_limit
            existing.credit_period_days = credit_days
            updated_count += 1
        else:
            cust = Customer(
                code=code,
                name=name,
                name_ar=name_ar,
                customer_type=cust_type,
                phone=phone,
                email=email,
                tax_number=tax_num,
                credit_limit=credit_limit,
                credit_period_days=credit_days
            )
            db.add(cust)
            imported_count += 1

    db.commit()
    return {
        "success": True,
        "imported": imported_count,
        "updated": updated_count,
        "total_processed": imported_count + updated_count,
        "errors": errors
    }

def import_items_from_bytes(file_bytes: bytes, filename: str, db: Session, user_id: int) -> Dict[str, Any]:
    rows = []
    if filename.endswith(".csv"):
        text = file_bytes.decode('utf-8-sig', errors='ignore')
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if len(rows) > 0:
            rows = rows[1:]  # skip header
    else:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_row=2, values_only=True):
            if any(row):
                rows.append(list(row))

    imported_count = 0
    updated_count = 0
    errors = []

    uom_cache = {u.code.upper(): u.id for u in db.query(UnitOfMeasure).all()}
    default_uom_id = next(iter(uom_cache.values())) if uom_cache else 1

    for idx, r in enumerate(rows, 2):
        if not r or not r[0]:
            continue
        sku = str(r[0]).strip()
        name = str(r[1]).strip() if len(r) > 1 and r[1] else sku
        name_ar = str(r[2]).strip() if len(r) > 2 and r[2] else name
        cat = str(r[3]).strip().upper() if len(r) > 3 and r[3] else "RAW_COFFEE"
        uom_code = str(r[4]).strip().upper() if len(r) > 4 and r[4] else "KG"
        uom_id = uom_cache.get(uom_code, default_uom_id)

        try:
            cost_price = Decimal(str(r[5])) if len(r) > 5 and r[5] is not None else Decimal('0.00')
        except Exception:
            cost_price = Decimal('0.00')

        try:
            selling_price = Decimal(str(r[6])) if len(r) > 6 and r[6] is not None else Decimal('0.00')
        except Exception:
            selling_price = Decimal('0.00')

        try:
            reorder_lvl = Decimal(str(r[7])) if len(r) > 7 and r[7] is not None else Decimal('0.00')
        except Exception:
            reorder_lvl = Decimal('0.00')

        existing = db.query(Item).filter(Item.sku == sku).first()
        if existing:
            existing.name = name
            existing.name_ar = name_ar
            existing.category = cat
            existing.uom_id = uom_id
            existing.cost_price = cost_price
            existing.selling_price = selling_price
            existing.reorder_level = reorder_lvl
            updated_count += 1
        else:
            item = Item(
                sku=sku,
                name=name,
                name_ar=name_ar,
                category=cat,
                uom_id=uom_id,
                cost_price=cost_price,
                selling_price=selling_price,
                reorder_level=reorder_lvl,
                is_active=True
            )
            db.add(item)
            imported_count += 1

    db.commit()
    return {
        "success": True,
        "imported": imported_count,
        "updated": updated_count,
        "total_processed": imported_count + updated_count,
        "errors": errors
    }

def import_stock_balances_from_bytes(file_bytes: bytes, filename: str, db: Session, user_id: int) -> Dict[str, Any]:
    rows = []
    if filename.endswith(".csv"):
        text = file_bytes.decode('utf-8-sig', errors='ignore')
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if len(rows) > 0:
            rows = rows[1:]  # skip header
    else:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_row=2, values_only=True):
            if any(row):
                rows.append(list(row))

    imported_count = 0
    errors = []
    wh_cache = {w.code.upper(): w.id for w in db.query(Warehouse).all()}

    for idx, r in enumerate(rows, 2):
        if not r or not r[0] or len(r) < 3:
            continue
        sku = str(r[0]).strip()
        wh_code = str(r[1]).strip().upper()
        
        try:
            qty = Decimal(str(r[2]))
        except Exception:
            continue
            
        unit_cost = None
        if len(r) > 3 and r[3] is not None:
            try:
                unit_cost = Decimal(str(r[3]))
            except Exception:
                unit_cost = None

        item = db.query(Item).filter(Item.sku == sku).first()
        if not item:
            errors.append(f"Row {idx}: Item SKU '{sku}' not found in catalog")
            continue

        wh_id = wh_cache.get(wh_code)
        if not wh_id:
            errors.append(f"Row {idx}: Warehouse '{wh_code}' not found")
            continue

        if unit_cost is None:
            unit_cost = item.cost_price

        # Update or create Quant
        record_stock_movement(
            db=db,
            item_id=item.id,
            from_warehouse_id=None,
            to_warehouse_id=wh_id,
            quantity=qty,
            uom_id=item.uom_id,
            unit_cost=unit_cost,
            move_type="OPENING_BALANCE",
            reference=f"Bulk Initial Inventory Import (Line {idx})",
            created_by_id=user_id
        )
        imported_count += 1

    db.commit()
    return {
        "success": True,
        "imported": imported_count,
        "errors": errors
    }
