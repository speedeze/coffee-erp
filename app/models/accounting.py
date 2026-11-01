from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Text, Numeric
from sqlalchemy.orm import relationship
from app.database import Base

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(120), nullable=False)
    name_ar = Column(String(120), nullable=False)
    type = Column(String(30), nullable=False)  # ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE
    category = Column(String(50), nullable=False)  # CURRENT_ASSET, INVENTORY, RECEIVABLE, CURRENT_LIABILITY, PAYABLE, EQUITY, TRADING_REVENUE, COGS, EXPENSE
    parent_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    parent = relationship("Account", remote_side=[id], backref="children")
    journal_items = relationship("JournalItem", back_populates="account")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "name_ar": self.name_ar,
            "type": self.type,
            "category": self.category,
            "parent_id": self.parent_id,
            "is_active": self.is_active
        }

class FinancialPeriod(Base):
    __tablename__ = "financial_periods"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    is_closed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, index=True)
    entry_number = Column(String(50), unique=True, index=True, nullable=False)
    date = Column(Date, default=date.today, index=True, nullable=False)
    reference = Column(String(120), nullable=True)
    source_document = Column(String(50), nullable=True)  # MANUAL, PURCHASE, ROASTING, PACKAGING, INVOICE, PAYMENT, RECEIPT
    source_id = Column(Integer, nullable=True)
    narration = Column(Text, nullable=True)
    status = Column(String(20), default="POSTED", index=True)  # DRAFT, POSTED, CANCELLED
    total_debit = Column(Numeric(14, 2), default=Decimal('0.00'))
    total_credit = Column(Numeric(14, 2), default=Decimal('0.00'))
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by_id])
    items = relationship("JournalItem", back_populates="entry", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "entry_number": self.entry_number,
            "date": self.date.strftime("%Y-%m-%d") if self.date else None,
            "reference": self.reference,
            "source_document": self.source_document,
            "source_id": self.source_id,
            "narration": self.narration,
            "status": self.status,
            "total_debit": float(self.total_debit or 0),
            "total_credit": float(self.total_credit or 0),
            "created_by": self.creator.username if self.creator else "System",
            "items": [item.to_dict() for item in self.items]
        }

class JournalItem(Base):
    __tablename__ = "journal_items"

    id = Column(Integer, primary_key=True, index=True)
    entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    description = Column(String(255), nullable=True)
    debit = Column(Numeric(14, 2), default=Decimal('0.00'), nullable=False)
    credit = Column(Numeric(14, 2), default=Decimal('0.00'), nullable=False)

    # Relationships
    entry = relationship("JournalEntry", back_populates="items")
    account = relationship("Account", back_populates="journal_items")

    def to_dict(self):
        return {
            "id": self.id,
            "account_id": self.account_id,
            "account_code": self.account.code if self.account else "",
            "account_name": self.account.name if self.account else "",
            "account_name_ar": self.account.name_ar if self.account else "",
            "description": self.description,
            "debit": float(self.debit or 0),
            "credit": float(self.credit or 0)
        }
