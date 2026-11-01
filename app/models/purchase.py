from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Text, Numeric
from sqlalchemy.orm import relationship
from app.database import Base

class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), unique=True, index=True, nullable=False)
    name = Column(String(120), nullable=False)
    name_ar = Column(String(120), nullable=False)
    country = Column(String(60), default="Local")
    is_foreign = Column(Boolean, default=False)
    currency = Column(String(10), default="USD")
    phone = Column(String(30), nullable=True)
    email = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    is_active = Column(Boolean, default=True)

    account = relationship("Account")
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "name_ar": self.name_ar,
            "country": self.country,
            "is_foreign": self.is_foreign,
            "currency": self.currency,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "is_active": self.is_active
        }

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(50), unique=True, index=True, nullable=False)
    date = Column(Date, default=date.today, index=True, nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    status = Column(String(20), default="DRAFT", index=True)  # DRAFT, RECEIVED, CANCELLED
    bill_of_lading = Column(String(100), nullable=True)
    currency = Column(String(10), default="USD")
    exchange_rate = Column(Numeric(12, 4), default=Decimal('1.0000'))
    
    subtotal_fob = Column(Numeric(14, 2), default=Decimal('0.00'))
    total_landed_costs = Column(Numeric(14, 2), default=Decimal('0.00'))
    grand_total = Column(Numeric(14, 2), default=Decimal('0.00'))
    
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    received_at = Column(DateTime, nullable=True)

    supplier = relationship("Supplier", back_populates="purchase_orders")
    warehouse = relationship("Warehouse")
    creator = relationship("User")
    journal_entry = relationship("JournalEntry")
    items = relationship("PurchaseOrderItem", back_populates="order", cascade="all, delete-orphan")
    landed_costs = relationship("LandedCost", back_populates="order", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "order_number": self.order_number,
            "date": self.date.strftime("%Y-%m-%d") if self.date else None,
            "supplier_id": self.supplier_id,
            "supplier_name": self.supplier.name if self.supplier else "",
            "supplier_name_ar": self.supplier.name_ar if self.supplier else "",
            "status": self.status,
            "bill_of_lading": self.bill_of_lading,
            "currency": self.currency,
            "exchange_rate": float(self.exchange_rate or 1),
            "subtotal_fob": float(self.subtotal_fob or 0),
            "total_landed_costs": float(self.total_landed_costs or 0),
            "grand_total": float(self.grand_total or 0),
            "warehouse_name": self.warehouse.name if self.warehouse else "",
            "journal_entry_number": self.journal_entry.entry_number if self.journal_entry else None,
            "items_count": len(self.items),
            "created_by": self.creator.username if self.creator else "System",
            "items": [i.to_dict() for i in self.items],
            "landed_costs": [lc.to_dict() for lc in self.landed_costs]
        }

class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    quantity = Column(Numeric(14, 4), nullable=False)
    uom_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=False)
    unit_price = Column(Numeric(14, 4), nullable=False)
    subtotal = Column(Numeric(14, 2), nullable=False)
    allocated_landed_cost = Column(Numeric(14, 2), default=Decimal('0.00'))
    effective_unit_cost = Column(Numeric(14, 4), default=Decimal('0.0000'))

    order = relationship("PurchaseOrder", back_populates="items")
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
            "subtotal": float(self.subtotal or 0),
            "allocated_landed_cost": float(self.allocated_landed_cost or 0),
            "effective_unit_cost": float(self.effective_unit_cost or 0)
        }

class LandedCost(Base):
    __tablename__ = "landed_costs"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    cost_type = Column(String(50), nullable=False)  # FREIGHT, CUSTOMS, PORT_HANDLING, CLEARANCE, INSURANCE, TRANSPORT
    cost_type_ar = Column(String(100), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    vendor_name = Column(String(100), nullable=True)
    allocation_method = Column(String(30), default="WEIGHT")  # WEIGHT or VALUE
    notes = Column(String(200), nullable=True)

    order = relationship("PurchaseOrder", back_populates="landed_costs")

    def to_dict(self):
        return {
            "id": self.id,
            "cost_type": self.cost_type,
            "cost_type_ar": self.cost_type_ar,
            "amount": float(self.amount or 0),
            "vendor_name": self.vendor_name,
            "allocation_method": self.allocation_method,
            "notes": self.notes
        }
