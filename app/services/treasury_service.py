from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.treasury import TreasuryAccount, ReceiptVoucher, PaymentVoucher
from app.models.sales import SalesInvoice
from app.models.accounting import Account
from app.services.accounting_service import create_balanced_journal_entry

def process_receipt_voucher(
    db: Session,
    voucher_date: date,
    treasury_account_id: int,
    amount: Decimal,
    credit_account_id: int,
    customer_id: Optional[int] = None,
    invoice_id: Optional[int] = None,
    description: Optional[str] = None,
    payer_name: Optional[str] = None,
    user_id: Optional[int] = None
) -> ReceiptVoucher:
    treasury_acc = db.query(TreasuryAccount).filter(TreasuryAccount.id == treasury_account_id).first()
    if not treasury_acc:
        raise ValueError("Treasury account not found")

    count = db.query(func.count(ReceiptVoucher.id)).scalar() or 0
    voucher_num = f"REC-{date.today().year}-{(count + 1):04d}"

    voucher = ReceiptVoucher(
        voucher_number=voucher_num,
        date=voucher_date,
        treasury_account_id=treasury_account_id,
        customer_id=customer_id,
        invoice_id=invoice_id,
        credit_account_id=credit_account_id,
        amount=amount,
        description=description,
        payer_name=payer_name,
        created_by_id=user_id
    )
    db.add(voucher)
    db.flush()

    # If linked to an invoice, update paid_amount
    if invoice_id:
        invoice = db.query(SalesInvoice).filter(SalesInvoice.id == invoice_id).first()
        if invoice:
            invoice.paid_amount = (Decimal(str(invoice.paid_amount or 0)) + amount).quantize(Decimal('0.01'))
            if invoice.paid_amount >= Decimal(str(invoice.total_amount)):
                invoice.status = "PAID"

    # Automated Double-Entry Journal:
    # Debit: Treasury / Bank Account (1110 or 1120)
    # Credit: Accounts Receivable (1210) or selected credit account
    cash_gl_account_id = treasury_acc.account_id

    journal_lines = [
        {
            "account_id": cash_gl_account_id,
            "debit": amount,
            "credit": Decimal('0.00'),
            "description": f"Receipt Voucher {voucher_num}: Received into {treasury_acc.name}"
        },
        {
            "account_id": credit_account_id,
            "debit": Decimal('0.00'),
            "credit": amount,
            "description": f"Receipt Voucher {voucher_num}: From {payer_name or 'Customer'}"
        }
    ]

    journal_entry = create_balanced_journal_entry(
        db=db,
        entry_date=voucher_date,
        reference=voucher_num,
        source_document="RECEIPT",
        source_id=voucher.id,
        narration=f"Cash Receipt Voucher {voucher_num} - {description or ''}",
        lines=journal_lines,
        created_by_id=user_id
    )
    voucher.journal_entry_id = journal_entry.id

    db.flush()
    return voucher

def process_payment_voucher(
    db: Session,
    voucher_date: date,
    treasury_account_id: int,
    amount: Decimal,
    debit_account_id: int,
    supplier_id: Optional[int] = None,
    purchase_order_id: Optional[int] = None,
    description: Optional[str] = None,
    beneficiary_name: Optional[str] = None,
    user_id: Optional[int] = None
) -> PaymentVoucher:
    treasury_acc = db.query(TreasuryAccount).filter(TreasuryAccount.id == treasury_account_id).first()
    if not treasury_acc:
        raise ValueError("Treasury account not found")

    count = db.query(func.count(PaymentVoucher.id)).scalar() or 0
    voucher_num = f"PAY-{date.today().year}-{(count + 1):04d}"

    voucher = PaymentVoucher(
        voucher_number=voucher_num,
        date=voucher_date,
        treasury_account_id=treasury_account_id,
        supplier_id=supplier_id,
        purchase_order_id=purchase_order_id,
        debit_account_id=debit_account_id,
        amount=amount,
        description=description,
        beneficiary_name=beneficiary_name,
        created_by_id=user_id
    )
    db.add(voucher)
    db.flush()

    # Automated Double-Entry Journal:
    # Debit: Supplier / Expense Account (debit_account_id)
    # Credit: Treasury / Bank Account (1110 or 1120)
    cash_gl_account_id = treasury_acc.account_id

    journal_lines = [
        {
            "account_id": debit_account_id,
            "debit": amount,
            "credit": Decimal('0.00'),
            "description": f"Payment Voucher {voucher_num}: Paid to {beneficiary_name or 'Vendor'}"
        },
        {
            "account_id": cash_gl_account_id,
            "debit": Decimal('0.00'),
            "credit": amount,
            "description": f"Payment Voucher {voucher_num}: Disbursed from {treasury_acc.name}"
        }
    ]

    journal_entry = create_balanced_journal_entry(
        db=db,
        entry_date=voucher_date,
        reference=voucher_num,
        source_document="PAYMENT",
        source_id=voucher.id,
        narration=f"Cash Payment Voucher {voucher_num} - {description or ''}",
        lines=journal_lines,
        created_by_id=user_id
    )
    voucher.journal_entry_id = journal_entry.id

    db.flush()
    return voucher
