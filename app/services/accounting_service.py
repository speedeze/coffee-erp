from datetime import date, datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from app.models.accounting import Account, JournalEntry, JournalItem
from app.models.inventory import StockQuant, Item

def generate_entry_number(db: Session) -> str:
    year = date.today().year
    count = db.query(func.count(JournalEntry.id)).filter(
        JournalEntry.entry_number.like(f"JE-{year}-%")
    ).scalar() or 0
    return f"JE-{year}-{(count + 1):04d}"

def create_balanced_journal_entry(
    db: Session,
    entry_date: date,
    reference: str,
    source_document: str,
    source_id: Optional[int],
    narration: str,
    lines: List[Dict[str, Any]],
    created_by_id: Optional[int] = None
) -> JournalEntry:
    """
    Creates a double-entry journal entry with strict balance validation (Debit == Credit).
    lines: List of dicts with:
      account_id: int
      debit: float/Decimal
      credit: float/Decimal
      description: str (optional)
    """
    total_debit = Decimal('0.00')
    total_credit = Decimal('0.00')

    cleaned_lines = []
    for line in lines:
        deb = Decimal(str(line.get('debit', 0) or 0)).quantize(Decimal('0.01'))
        cred = Decimal(str(line.get('credit', 0) or 0)).quantize(Decimal('0.01'))
        if deb == 0 and cred == 0:
            continue
        total_debit += deb
        total_credit += cred
        cleaned_lines.append({
            "account_id": line['account_id'],
            "debit": deb,
            "credit": cred,
            "description": line.get('description', '')
        })

    # Validate Double-Entry Balance
    if abs(total_debit - total_credit) > Decimal('0.01'):
        raise ValueError(
            f"Unbalanced Journal Entry! Total Debit: {total_debit} does not match Total Credit: {total_credit}"
        )

    entry = JournalEntry(
        entry_number=generate_entry_number(db),
        date=entry_date,
        reference=reference,
        source_document=source_document,
        source_id=source_id,
        narration=narration,
        status="POSTED",
        total_debit=total_debit,
        total_credit=total_credit,
        created_by_id=created_by_id
    )
    db.add(entry)
    db.flush()

    for item_data in cleaned_lines:
        item = JournalItem(
            entry_id=entry.id,
            account_id=item_data['account_id'],
            description=item_data['description'],
            debit=item_data['debit'],
            credit=item_data['credit']
        )
        db.add(item)

    db.flush()
    return entry

def get_general_ledger(
    db: Session,
    account_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> Dict[str, Any]:
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise ValueError("Account not found")

    # Calculate Opening Balance before start_date
    opening_balance = Decimal('0.00')
    if start_date:
        prior_items = db.query(
            func.coalesce(func.sum(JournalItem.debit), 0).label("prior_debit"),
            func.coalesce(func.sum(JournalItem.credit), 0).label("prior_credit")
        ).join(JournalEntry).filter(
            JournalItem.account_id == account_id,
            JournalEntry.status == "POSTED",
            JournalEntry.date < start_date
        ).first()

        prior_deb = Decimal(str(prior_items.prior_debit or 0))
        prior_cred = Decimal(str(prior_items.prior_credit or 0))

        if account.type in ["ASSET", "EXPENSE"]:
            opening_balance = prior_deb - prior_cred
        else:
            opening_balance = prior_cred - prior_deb

    # Query period journal items
    query = db.query(JournalItem, JournalEntry).join(JournalEntry).filter(
        JournalItem.account_id == account_id,
        JournalEntry.status == "POSTED"
    )

    if start_date:
        query = query.filter(JournalEntry.date >= start_date)
    if end_date:
        query = query.filter(JournalEntry.date <= end_date)

    query = query.order_by(JournalEntry.date.asc(), JournalEntry.id.asc(), JournalItem.id.asc())
    records = query.all()

    running_balance = opening_balance
    lines = []
    total_debit = Decimal('0.00')
    total_credit = Decimal('0.00')

    for item, entry in records:
        deb = Decimal(str(item.debit or 0))
        cred = Decimal(str(item.credit or 0))
        total_debit += deb
        total_credit += cred

        if account.type in ["ASSET", "EXPENSE"]:
            running_balance += (deb - cred)
        else:
            running_balance += (cred - deb)

        lines.append({
            "item_id": item.id,
            "entry_id": entry.id,
            "date": entry.date.strftime("%Y-%m-%d"),
            "entry_number": entry.entry_number,
            "reference": entry.reference or "-",
            "description": item.description or entry.narration or "-",
            "debit": float(deb),
            "credit": float(cred),
            "running_balance": float(running_balance)
        })

    return {
        "account": account.to_dict(),
        "opening_balance": float(opening_balance),
        "total_debit": float(total_debit),
        "total_credit": float(total_credit),
        "closing_balance": float(running_balance),
        "lines": lines
    }

def get_trial_balance(
    db: Session,
    as_of_date: Optional[date] = None,
    include_zero_balances: bool = True
) -> Dict[str, Any]:
    """
    Computes Trial Balance (ميزان المراجعة بالمجاميع والأرصدة):
    Accurately computes total debit, total credit, and final balances
    for all parent and sub-accounts with full hierarchy rollup.
    """
    accounts = db.query(Account).order_by(Account.code.asc()).all()
    
    # Map accounts and determine hierarchy
    acc_map = {}
    for acc in accounts:
        code = acc.code.strip()
        if code.endswith("000"):
            level = 1
            is_parent = True
            parent_code = None
        elif code.endswith("00"):
            level = 2
            is_parent = True
            parent_code = code[0] + "000"
        else:
            level = 3
            is_parent = False
            parent_code = code[:2] + "00"

        acc_map[code] = {
            "id": acc.id,
            "code": code,
            "name": acc.name,
            "name_ar": acc.name_ar,
            "type": acc.type,
            "category": acc.category,
            "level": level,
            "is_parent": is_parent,
            "parent_code": parent_code,
            "direct_debit": Decimal('0.00'),
            "direct_credit": Decimal('0.00'),
            "total_debit": Decimal('0.00'),
            "total_credit": Decimal('0.00'),
            "net_debit": Decimal('0.00'),
            "net_credit": Decimal('0.00')
        }

    # If any account has another account claiming it as parent_code, ensure is_parent is True
    for item in acc_map.values():
        p_code = item["parent_code"]
        if p_code and p_code in acc_map:
            acc_map[p_code]["is_parent"] = True

    # 1. Fetch direct journal items for each account
    for acc in accounts:
        query = db.query(
            func.coalesce(func.sum(JournalItem.debit), 0).label("sum_debit"),
            func.coalesce(func.sum(JournalItem.credit), 0).label("sum_credit")
        ).join(JournalEntry).filter(
            JournalItem.account_id == acc.id,
            JournalEntry.status == "POSTED"
        )
        if as_of_date:
            query = query.filter(JournalEntry.date <= as_of_date)

        res = query.first()
        deb = Decimal(str(res.sum_debit or 0)).quantize(Decimal('0.01'))
        cred = Decimal(str(res.sum_credit or 0)).quantize(Decimal('0.01'))

        acc_map[acc.code]["direct_debit"] = deb
        acc_map[acc.code]["direct_credit"] = cred
        acc_map[acc.code]["total_debit"] = deb
        acc_map[acc.code]["total_credit"] = cred

    # 2. Roll up child movements into parents
    # Process from Level 3 to Level 1
    for code, item in sorted(acc_map.items(), key=lambda x: x[1]["level"], reverse=True):
        p_code = item["parent_code"]
        if p_code and p_code in acc_map:
            acc_map[p_code]["total_debit"] += item["total_debit"]
            acc_map[p_code]["total_credit"] += item["total_credit"]

    # 3. Calculate net ending balances (Debits & Credits) for all accounts
    grand_total_debit_balance = Decimal('0.00')
    grand_total_credit_balance = Decimal('0.00')
    grand_movement_debit = Decimal('0.00')
    grand_movement_credit = Decimal('0.00')

    rows = []
    for code, item in sorted(acc_map.items(), key=lambda x: x[0]):
        deb = item["total_debit"]
        cred = item["total_credit"]

        net_deb = Decimal('0.00')
        net_cred = Decimal('0.00')

        if item["type"] in ["ASSET", "EXPENSE"]:
            net = deb - cred
            if net >= 0:
                net_deb = net
            else:
                net_cred = abs(net)
        else:
            net = cred - deb
            if net >= 0:
                net_cred = net
            else:
                net_deb = abs(net)

        item["net_debit"] = net_deb
        item["net_credit"] = net_cred

        # Leaf accounts contribute to the grand totals
        if not item["is_parent"] or (item["direct_debit"] > 0 and item["total_debit"] == item["direct_debit"]):
            grand_total_debit_balance += net_deb
            grand_total_credit_balance += net_cred
            grand_movement_debit += deb
            grand_movement_credit += cred

        has_activity = (deb > 0 or cred > 0 or net_deb > 0 or net_cred > 0)
        
        if include_zero_balances or has_activity:
            rows.append({
                "code": item["code"],
                "name": item["name"],
                "name_ar": item["name_ar"],
                "type": item["type"],
                "category": item["category"],
                "level": item["level"],
                "is_parent": item["is_parent"],
                "parent_code": item["parent_code"],
                "total_debit": float(deb),
                "total_credit": float(cred),
                "net_debit": float(net_deb),
                "net_credit": float(net_cred),
                "has_activity": has_activity
            })

    is_balanced = abs(grand_total_debit_balance - grand_total_credit_balance) < Decimal('0.01')

    return {
        "as_of_date": as_of_date.strftime("%Y-%m-%d") if as_of_date else date.today().strftime("%Y-%m-%d"),
        "total_debit": float(grand_total_debit_balance),
        "total_credit": float(grand_total_credit_balance),
        "movement_debit": float(grand_movement_debit),
        "movement_credit": float(grand_movement_credit),
        "is_balanced": is_balanced,
        "rows": rows
    }

def get_income_statement(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> Dict[str, Any]:
    """
    Computes Income Statement / Profit & Loss (قائمة الأرباح والخسائر):
    Revenues - Cost of Goods Sold = Gross Profit
    Gross Profit - Operating/Roasting Expenses = Net Operating Profit
    """
    def get_account_net(acc_type, category=None):
        query = db.query(
            Account,
            func.coalesce(func.sum(JournalItem.debit), 0).label("deb"),
            func.coalesce(func.sum(JournalItem.credit), 0).label("cred")
        ).join(JournalItem, Account.id == JournalItem.account_id).join(JournalEntry).filter(
            Account.type == acc_type,
            JournalEntry.status == "POSTED"
        )
        if category:
            query = query.filter(Account.category == category)
        if start_date:
            query = query.filter(JournalEntry.date >= start_date)
        if end_date:
            query = query.filter(JournalEntry.date <= end_date)
        
        query = query.group_by(Account.id)
        results = query.all()
        
        items = []
        category_total = Decimal('0.00')
        for acc, deb, cred in results:
            d = Decimal(str(deb))
            c = Decimal(str(cred))
            net = (c - d) if acc_type == "REVENUE" else (d - c)
            if net != 0:
                category_total += net
                items.append({
                    "code": acc.code,
                    "name": acc.name,
                    "name_ar": acc.name_ar,
                    "amount": float(net)
                })
        return items, category_total

    revenues, total_revenue = get_account_net("REVENUE")
    cogs_items, total_cogs = get_account_net("EXPENSE", "COGS")
    gross_profit = total_revenue - total_cogs

    expenses, total_expenses = get_account_net("EXPENSE")
    # Filter out COGS from general expenses since COGS is already deducted above
    non_cogs_expenses = [e for e in expenses if not any(c['code'] == e['code'] for c in cogs_items)]
    total_operating_expenses = sum([Decimal(str(e['amount'])) for e in non_cogs_expenses])
    net_profit = gross_profit - total_operating_expenses

    return {
        "start_date": start_date.strftime("%Y-%m-%d") if start_date else None,
        "end_date": end_date.strftime("%Y-%m-%d") if end_date else date.today().strftime("%Y-%m-%d"),
        "revenues": revenues,
        "total_revenue": float(total_revenue),
        "cogs_items": cogs_items,
        "total_cogs": float(total_cogs),
        "gross_profit": float(gross_profit),
        "operating_expenses": non_cogs_expenses,
        "total_operating_expenses": float(total_operating_expenses),
        "net_profit": float(net_profit)
    }

def get_trading_account(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> Dict[str, Any]:
    """
    Trading Account (حساب المتاجرة):
    Debit Side:
      - Opening Inventory
      - Purchases (Raw Green Coffee + Additives + Packaging)
      - Direct Import Expenses / Freight & Customs
    Credit Side:
      - Wholesale Sales Revenues
      - Closing Inventory
    Result: Gross Trading Profit / Loss
    """
    # 1. Wholesale Sales
    sales_query = db.query(
        Account,
        func.coalesce(func.sum(JournalItem.credit - JournalItem.debit), 0).label("net_sales")
    ).join(JournalItem, Account.id == JournalItem.account_id).join(JournalEntry).filter(
        Account.type == "REVENUE",
        JournalEntry.status == "POSTED"
    )
    if start_date:
        sales_query = sales_query.filter(JournalEntry.date >= start_date)
    if end_date:
        sales_query = sales_query.filter(JournalEntry.date <= end_date)
    sales_rows = sales_query.group_by(Account.id).all()
    sales_total = sum([Decimal(str(r.net_sales or 0)) for r in sales_rows])

    # 2. Current Perpetual Inventory Value (Closing Inventory)
    inventory_quants = db.query(StockQuant, Item).join(Item).all()
    closing_inventory_val = Decimal('0.00')
    inventory_breakdown = []
    for quant, item in inventory_quants:
        qty = Decimal(str(quant.quantity or 0))
        cost = Decimal(str(item.cost_price or 0))
        val = (qty * cost).quantize(Decimal('0.01'))
        if val > 0:
            closing_inventory_val += val
            inventory_breakdown.append({
                "item_name": item.name,
                "item_name_ar": item.name_ar,
                "quantity": float(qty),
                "cost_price": float(cost),
                "value": float(val)
            })

    # 3. Cost of Goods Sold from Journals
    cogs_query = db.query(
        Account,
        func.coalesce(func.sum(JournalItem.debit - JournalItem.credit), 0).label("cogs")
    ).join(JournalItem, Account.id == JournalItem.account_id).join(JournalEntry).filter(
        Account.category == "COGS",
        JournalEntry.status == "POSTED"
    )
    if start_date:
        cogs_query = cogs_query.filter(JournalEntry.date >= start_date)
    if end_date:
        cogs_query = cogs_query.filter(JournalEntry.date <= end_date)
    cogs_rows = cogs_query.group_by(Account.id).all()
    total_cogs = sum([Decimal(str(r.cogs or 0)) for r in cogs_rows])

    gross_trading_profit = sales_total - total_cogs

    return {
        "start_date": start_date.strftime("%Y-%m-%d") if start_date else None,
        "end_date": end_date.strftime("%Y-%m-%d") if end_date else date.today().strftime("%Y-%m-%d"),
        "sales_total": float(sales_total),
        "closing_inventory_value": float(closing_inventory_val),
        "total_cogs": float(total_cogs),
        "gross_trading_profit": float(gross_trading_profit),
        "inventory_breakdown": inventory_breakdown
    }

def get_balance_sheet(db: Session, as_of_date: Optional[date] = None) -> Dict[str, Any]:
    """
    Statement of Financial Position / Balance Sheet (قائمة المركز المالي):
    Assets = Liabilities + Equity (including current period retained earnings)
    """
    tb = get_trial_balance(db, as_of_date)
    assets = []
    liabilities = []
    equity = []
    current_pnl = Decimal('0.00')

    total_assets = Decimal('0.00')
    total_liabilities = Decimal('0.00')
    total_equity = Decimal('0.00')

    for r in tb['rows']:
        # Skip rollup parent accounts to avoid double-counting
        if r.get('is_parent'):
            continue

        net_deb = Decimal(str(r['net_debit']))
        net_cred = Decimal(str(r['net_credit']))

        if r['type'] == 'ASSET':
            val = net_deb - net_cred
            if val != 0:
                total_assets += val
                assets.append({"code": r['code'], "name": r['name'], "name_ar": r['name_ar'], "amount": float(val)})
        elif r['type'] == 'LIABILITY':
            val = net_cred - net_deb
            if val != 0:
                total_liabilities += val
                liabilities.append({"code": r['code'], "name": r['name'], "name_ar": r['name_ar'], "amount": float(val)})
        elif r['type'] == 'EQUITY':
            val = net_cred - net_deb
            if val != 0:
                total_equity += val
                equity.append({"code": r['code'], "name": r['name'], "name_ar": r['name_ar'], "amount": float(val)})
        elif r['type'] == 'REVENUE':
            current_pnl += (net_cred - net_deb)
        elif r['type'] == 'EXPENSE':
            current_pnl -= (net_deb - net_cred)

    # Net profit of current period added to equity
    total_equity_with_pnl = total_equity + current_pnl
    total_liab_and_equity = total_liabilities + total_equity_with_pnl

    return {
        "as_of_date": as_of_date.strftime("%Y-%m-%d") if as_of_date else date.today().strftime("%Y-%m-%d"),
        "assets": assets,
        "total_assets": float(total_assets),
        "liabilities": liabilities,
        "total_liabilities": float(total_liabilities),
        "equity": equity,
        "base_equity": float(total_equity),
        "current_period_pnl": float(current_pnl),
        "total_equity": float(total_equity_with_pnl),
        "total_liabilities_and_equity": float(total_liab_and_equity),
        "is_balanced": abs(total_assets - total_liab_and_equity) < Decimal('0.01')
    }
