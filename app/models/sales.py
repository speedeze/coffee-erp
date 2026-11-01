from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Text, Numeric
from sqlalchemy.orm import relationship
from app.database import Base

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), unique=True, index=True, nullable=False)
    name = Column(String(120), nullable=False)
    name_ar = Column(String(120), nullable=False)
    customer_type = Column(String(30), default="CAFE")  # CAFE, WHOLESALER, HOTEL, RETAILER, CORPORATE
    phone = Column(String(30), nullable=True)
    email = Column(String(100), nullable=True)
    tax_number = Column(String(50), nullable=True)
    credit_limit = Column(Numeric(14, 2), default=Decimal('0.00'))
    credit_period_days = Column(Integer, default=30)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    is_active = Column(Boolean, default=True)

    account = relationship("Account")
    invoices = relationship("SalesInvoice", back_populates="customer")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "name_ar": self.name_ar,
            "customer_type": self.customer_type,
            "phone": self.phone,
            "email": self.email,
            "tax_number": self.tax_number,
            "credit_limit": float(self.credit_limit or 0),
            "credit_period_days": self.credit_period_days,
            "is_active": self.is_active
        }

class SalesInvoice(Base):
    __tablename__ = "sales_invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(50), unique=True, index=True, nullable=False)
    date = Column(Date, default=date.today, index=True, nullable=False)
    due_date = Column(Date, nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    payment_terms = Column(String(50), default="NET30")  # CASH, NET15, NET30, NET60
    status = Column(String(20), default="DRAFT", index=True)  # DRAFT, CONFIRMED, PAID, CANCELLED
    
    subtotal = Column(Numeric(14, 2), default=Decimal('0.00'))
    tax_rate = Column(Numeric(5, 2), default=Decimal('0.00'))
    tax_amount = Column(Numeric(14, 2), default=Decimal('0.00'))
    discount_amount = Column(Numeric(14, 2), default=Decimal('0.00'))
    total_amount = Column(Numeric(14, 2), default=Decimal('0.00'))
    paid_amount = Column(Numeric(14, 2), default=Decimal('0.00'))
    
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)

    customer = relationship("Customer", back_populates="invoices")
    warehouse = relationship("Warehouse")
    creator = relationship("User")
    journal_entry = relationship("JournalEntry")
    items = relationship("SalesInvoiceItem", back_populates="invoice", cascade="all, delete-orphan")

    def to_dict(self):
        balance_due = float(self.total_amount or 0) - float(self.paid_amount or 0)
        return {
            "id": self.id,
            "invoice_number": self.invoice_number,
            "date": self.date.strftime("%Y-%m-%d") if self.date else None,
            "due_date": self.due_date.strftime("%Y-%m-%d") if self.due_date else None,
            "customer_id": self.customer_id,
            "customer_name": self.customer.name if self.customer else "",
            "customer_name_ar": self.customer.name_ar if self.customer else "",
            "payment_terms": self.payment_terms,
            "status": self.status,
            "subtotal": float(self.subtotal or 0),
            "tax_rate": float(self.tax_rate or 0),
            "tax_amount": float(self.tax_amount or 0),
            "discount_amount": float(self.discount_amount or 0),
            "total_amount": float(self.total_amount or 0),
            "paid_amount": float(self.paid_amount or 0),
            "balance_due": round(balance_due, 2),
            "warehouse_name": self.warehouse.name if self.warehouse else "",
            "journal_entry_number": self.journal_entry.entry_number if self.journal_entry else None,
            "items_count": len(self.items),
            "created_by": self.creator.username if self.creator else "System",
            "items": [i.to_dict() for i in self.items],
            "notes": self.notes
        }

class SalesInvoiceItem(Base):
    __tablename__ = "sales_invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("sales_invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    quantity = Column(Numeric(14, 4), nullable=False)
    uom_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=False)
    unit_price = Column(Numeric(14, 2), nullable=False)
    unit_cost = Column(Numeric(14, 4), default=Decimal('0.0000'))  # Valuation snapshot
    subtotal = Column(Numeric(14, 2), nullable=False)

    invoice = relationship("SalesInvoice", back_populates="items")
    item = relationship("Item")
    uom = relationship("UnitOfMeasure")

    def to_dict(self):
        return {
            "id": self.id,
            "item_id": self.item_id,
            "item_name": self.item.name if self.item else "",
            "item_name_ar": self.item.name_ar if self.item else "",
            "quantity": float(self.quantity or 0),
            "uom_id": self.uom_id,
            "uom_code": self.uom.code if self.uom else "",
            "unit_price": float(self.unit_price or 0),
            "unit_cost": float(self.unit_cost or 0),
            "subtotal": float(self.subtotal or 0)
        }
