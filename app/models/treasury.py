from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Text, Numeric
from sqlalchemy.orm import relationship
from app.database import Base

class TreasuryAccount(Base):
    __tablename__ = "treasury_accounts"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    name_ar = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False)  # CASH, BANK
    currency = Column(String(10), default="USD")
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    is_active = Column(Boolean, default=True)

    account = relationship("Account")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "name_ar": self.name_ar,
            "type": self.type,
            "currency": self.currency,
            "account_id": self.account_id,
            "account_code": self.account.code if self.account else "",
            "account_name": self.account.name if self.account else "",
            "is_active": self.is_active
        }

class ReceiptVoucher(Base):
    __tablename__ = "receipt_vouchers"

    id = Column(Integer, primary_key=True, index=True)
    voucher_number = Column(String(50), unique=True, index=True, nullable=False)
    date = Column(Date, default=date.today, index=True, nullable=False)
    treasury_account_id = Column(Integer, ForeignKey("treasury_accounts.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    invoice_id = Column(Integer, ForeignKey("sales_invoices.id"), nullable=True)
    credit_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    description = Column(Text, nullable=True)
    payer_name = Column(String(120), nullable=True)
    
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    treasury_account = relationship("TreasuryAccount")
    customer = relationship("Customer")
    invoice = relationship("SalesInvoice")
    credit_account = relationship("Account")
    creator = relationship("User")
    journal_entry = relationship("JournalEntry")

    def to_dict(self):
        return {
            "id": self.id,
            "voucher_number": self.voucher_number,
            "date": self.date.strftime("%Y-%m-%d") if self.date else None,
            "treasury_account_name": self.treasury_account.name if self.treasury_account else "",
            "customer_name": self.customer.name if self.customer else self.payer_name,
            "customer_name_ar": self.customer.name_ar if self.customer else self.payer_name,
            "invoice_number": self.invoice.invoice_number if self.invoice else None,
            "credit_account_name": self.credit_account.name if self.credit_account else "",
            "amount": float(self.amount or 0),
            "description": self.description,
            "payer_name": self.payer_name,
            "journal_entry_number": self.journal_entry.entry_number if self.journal_entry else None,
            "created_by": self.creator.username if self.creator else "System"
        }

class PaymentVoucher(Base):
    __tablename__ = "payment_vouchers"

    id = Column(Integer, primary_key=True, index=True)
    voucher_number = Column(String(50), unique=True, index=True, nullable=False)
    date = Column(Date, default=date.today, index=True, nullable=False)
    treasury_account_id = Column(Integer, ForeignKey("treasury_accounts.id"), nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=True)
    debit_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    description = Column(Text, nullable=True)
    beneficiary_name = Column(String(120), nullable=True)
    
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    treasury_account = relationship("TreasuryAccount")
    supplier = relationship("Supplier")
    purchase_order = relationship("PurchaseOrder")
    debit_account = relationship("Account")
    creator = relationship("User")
    journal_entry = relationship("JournalEntry")

    def to_dict(self):
        return {
            "id": self.id,
            "voucher_number": self.voucher_number,
            "date": self.date.strftime("%Y-%m-%d") if self.date else None,
            "treasury_account_name": self.treasury_account.name if self.treasury_account else "",
            "supplier_name": self.supplier.name if self.supplier else self.beneficiary_name,
            "supplier_name_ar": self.supplier.name_ar if self.supplier else self.beneficiary_name,
            "purchase_order_number": self.purchase_order.order_number if self.purchase_order else None,
            "debit_account_name": self.debit_account.name if self.debit_account else "",
            "amount": float(self.amount or 0),
            "description": self.description,
            "beneficiary_name": self.beneficiary_name,
            "journal_entry_number": self.journal_entry.entry_number if self.journal_entry else None,
            "created_by": self.creator.username if self.creator else "System"
        }
