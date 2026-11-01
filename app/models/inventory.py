from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from app.database import Base

class UnitOfMeasure(Base):
    __tablename__ = "units_of_measure"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(50), nullable=False)
    name_ar = Column(String(50), nullable=False)
    category = Column(String(20), nullable=False)  # WEIGHT, UNIT
    ratio_to_base = Column(Numeric(12, 4), nullable=False)  # e.g., KG=1.0, G=0.001, TON=1000.0, BAG60=60.0

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "name_ar": self.name_ar,
            "category": self.category,
            "ratio_to_base": float(self.ratio_to_base)
        }

class Warehouse(Base):
    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    name_ar = Column(String(100), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)  # Associated inventory asset account
    is_active = Column(Boolean, default=True)

    account = relationship("Account")
    quants = relationship("StockQuant", back_populates="warehouse")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "name_ar": self.name_ar,
            "account_id": self.account_id,
            "account_code": self.account.code if self.account else "",
            "account_name": self.account.name if self.account else ""
        }

class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(120), nullable=False)
    name_ar = Column(String(120), nullable=False)
    category = Column(String(50), index=True, nullable=False)  # RAW_COFFEE, ROASTED_COFFEE, SPICE, PACKAGING, FINISHED_GOODS
    uom_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=False)
    cost_price = Column(Numeric(14, 4), default=Decimal('0.0000'))  # Weighted average cost per base UOM
    selling_price = Column(Numeric(14, 2), default=Decimal('0.00'))
    reorder_level = Column(Numeric(12, 2), default=Decimal('0.00'))
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    uom = relationship("UnitOfMeasure")
    account = relationship("Account")
    quants = relationship("StockQuant", back_populates="item")

    def to_dict(self):
        total_stock = sum([float(q.quantity or 0) for q in self.quants])
        return {
            "id": self.id,
            "sku": self.sku,
            "name": self.name,
            "name_ar": self.name_ar,
            "category": self.category,
            "uom_id": self.uom_id,
            "uom_code": self.uom.code if self.uom else "",
            "uom_name": self.uom.name if self.uom else "",
            "cost_price": float(self.cost_price or 0),
            "selling_price": float(self.selling_price or 0),
            "reorder_level": float(self.reorder_level or 0),
            "total_stock": total_stock,
            "stock_value": round(total_stock * float(self.cost_price or 0), 2),
            "is_active": self.is_active
        }

class StockQuant(Base):
    __tablename__ = "stock_quants"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True)
    quantity = Column(Numeric(14, 4), default=Decimal('0.0000'))
    reserved_quantity = Column(Numeric(14, 4), default=Decimal('0.0000'))

    item = relationship("Item", back_populates="quants")
    warehouse = relationship("Warehouse", back_populates="quants")

    def to_dict(self):
        return {
            "id": self.id,
            "item_id": self.item_id,
            "item_name": self.item.name if self.item else "",
            "item_sku": self.item.sku if self.item else "",
            "warehouse_id": self.warehouse_id,
            "warehouse_name": self.warehouse.name if self.warehouse else "",
            "quantity": float(self.quantity or 0),
            "reserved_quantity": float(self.reserved_quantity or 0)
        }

class StockMove(Base):
    __tablename__ = "stock_moves"

    id = Column(Integer, primary_key=True, index=True)
    move_number = Column(String(50), unique=True, index=True, nullable=False)
    date = Column(DateTime, default=datetime.utcnow, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)
    from_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    to_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    quantity = Column(Numeric(14, 4), nullable=False)
    uom_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=False)
    unit_cost = Column(Numeric(14, 4), default=Decimal('0.0000'))
    total_cost = Column(Numeric(14, 2), default=Decimal('0.00'))
    reference = Column(String(100), nullable=True)
    move_type = Column(String(50), nullable=False)  # PURCHASE_RECEIPT, ROASTING_IN, ROASTING_OUT, ROASTING_LOSS, PACKAGING_IN, PACKAGING_OUT, SALES_DISPATCH, ADJUSTMENT
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    item = relationship("Item")
    uom = relationship("UnitOfMeasure")
    from_warehouse = relationship("Warehouse", foreign_keys=[from_warehouse_id])
    to_warehouse = relationship("Warehouse", foreign_keys=[to_warehouse_id])
    creator = relationship("User", foreign_keys=[created_by_id])

    def to_dict(self):
        return {
            "id": self.id,
            "move_number": self.move_number,
            "date": self.date.strftime("%Y-%m-%d %H:%M") if self.date else None,
            "item_name": self.item.name if self.item else "",
            "item_name_ar": self.item.name_ar if self.item else "",
            "from_warehouse": self.from_warehouse.name if self.from_warehouse else "-",
            "to_warehouse": self.to_warehouse.name if self.to_warehouse else "-",
            "quantity": float(self.quantity or 0),
            "uom_code": self.uom.code if self.uom else "",
            "unit_cost": float(self.unit_cost or 0),
            "total_cost": float(self.total_cost or 0),
            "reference": self.reference,
            "move_type": self.move_type,
            "created_by": self.creator.username if self.creator else "System"
        }
