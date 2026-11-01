from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Text, Numeric
from sqlalchemy.orm import relationship
from app.database import Base

class RoastingOrder(Base):
    __tablename__ = "roasting_orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(50), unique=True, index=True, nullable=False)
    date = Column(Date, default=date.today, index=True, nullable=False)
    status = Column(String(20), default="DRAFT", index=True)  # DRAFT, COMPLETED, CANCELLED
    roast_profile = Column(String(50), default="Medium")  # Light, Medium, Medium-Dark, Dark
    
    # Input Raw Coffee
    raw_item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    raw_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    raw_quantity_kg = Column(Numeric(12, 4), nullable=False)
    raw_unit_cost = Column(Numeric(14, 4), nullable=False)
    total_raw_cost = Column(Numeric(14, 2), nullable=False)

    # Output Roasted Coffee
    roasted_item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    roasted_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    expected_shrinkage_pct = Column(Numeric(5, 2), default=Decimal('18.00'))
    actual_roasted_qty_kg = Column(Numeric(12, 4), nullable=True)
    actual_shrinkage_pct = Column(Numeric(5, 2), nullable=True)
    shrinkage_loss_kg = Column(Numeric(12, 4), nullable=True)
    
    # Cost Revaluation
    revalued_cost_per_kg = Column(Numeric(14, 4), nullable=True)
    additional_cost = Column(Numeric(14, 2), default=Decimal('0.00'))  # Gas/power absorption
    total_production_cost = Column(Numeric(14, 2), nullable=True)

    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    raw_item = relationship("Item", foreign_keys=[raw_item_id])
    roasted_item = relationship("Item", foreign_keys=[roasted_item_id])
    raw_warehouse = relationship("Warehouse", foreign_keys=[raw_warehouse_id])
    roasted_warehouse = relationship("Warehouse", foreign_keys=[roasted_warehouse_id])
    creator = relationship("User", foreign_keys=[created_by_id])
    journal_entry = relationship("JournalEntry", foreign_keys=[journal_entry_id])

    def to_dict(self):
        return {
            "id": self.id,
            "order_number": self.order_number,
            "date": self.date.strftime("%Y-%m-%d") if self.date else None,
            "status": self.status,
            "roast_profile": self.roast_profile,
            "raw_item_id": self.raw_item_id,
            "raw_item_name": self.raw_item.name if self.raw_item else "",
            "raw_item_name_ar": self.raw_item.name_ar if self.raw_item else "",
            "raw_warehouse_name": self.raw_warehouse.name if self.raw_warehouse else "",
            "raw_quantity_kg": float(self.raw_quantity_kg or 0),
            "raw_unit_cost": float(self.raw_unit_cost or 0),
            "total_raw_cost": float(self.total_raw_cost or 0),
            "roasted_item_id": self.roasted_item_id,
            "roasted_item_name": self.roasted_item.name if self.roasted_item else "",
            "roasted_item_name_ar": self.roasted_item.name_ar if self.roasted_item else "",
            "roasted_warehouse_name": self.roasted_warehouse.name if self.roasted_warehouse else "",
            "expected_shrinkage_pct": float(self.expected_shrinkage_pct or 0),
            "actual_roasted_qty_kg": float(self.actual_roasted_qty_kg or 0) if self.actual_roasted_qty_kg else None,
            "actual_shrinkage_pct": float(self.actual_shrinkage_pct or 0) if self.actual_shrinkage_pct else None,
            "shrinkage_loss_kg": float(self.shrinkage_loss_kg or 0) if self.shrinkage_loss_kg else None,
            "revalued_cost_per_kg": float(self.revalued_cost_per_kg or 0) if self.revalued_cost_per_kg else None,
            "total_production_cost": float(self.total_production_cost or 0) if self.total_production_cost else None,
            "journal_entry_id": self.journal_entry_id,
            "journal_entry_number": self.journal_entry.entry_number if self.journal_entry else None,
            "created_by": self.creator.username if self.creator else "System",
            "notes": self.notes
        }

class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(120), nullable=False)
    name_ar = Column(String(120), nullable=False)
    finished_item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    yield_quantity = Column(Numeric(12, 4), default=Decimal('1.0000'))
    yield_uom_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)

    finished_item = relationship("Item")
    yield_uom = relationship("UnitOfMeasure")
    items = relationship("RecipeItem", back_populates="recipe", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "name_ar": self.name_ar,
            "finished_item_id": self.finished_item_id,
            "finished_item_name": self.finished_item.name if self.finished_item else "",
            "finished_item_name_ar": self.finished_item.name_ar if self.finished_item else "",
            "yield_quantity": float(self.yield_quantity or 1),
            "yield_uom_code": self.yield_uom.code if self.yield_uom else "",
            "description": self.description,
            "items_count": len(self.items),
            "items": [i.to_dict() for i in self.items]
        }

class RecipeItem(Base):
    __tablename__ = "recipe_items"

    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    quantity = Column(Numeric(14, 4), nullable=False)
    uom_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=False)
    notes = Column(String(100), nullable=True)

    recipe = relationship("Recipe", back_populates="items")
    item = relationship("Item")
    uom = relationship("UnitOfMeasure")

    def to_dict(self):
        return {
            "id": self.id,
            "item_id": self.item_id,
            "item_name": self.item.name if self.item else "",
            "item_name_ar": self.item.name_ar if self.item else "",
            "item_category": self.item.category if self.item else "",
            "quantity": float(self.quantity or 0),
            "uom_id": self.uom_id,
            "uom_code": self.uom.code if self.uom else "",
            "cost_price": float(self.item.cost_price or 0) if self.item else 0,
            "subtotal_cost": round(float(self.quantity or 0) * float(self.item.cost_price or 0), 4) if self.item else 0,
            "notes": self.notes
        }

class ProductionOrder(Base):
    __tablename__ = "production_orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(50), unique=True, index=True, nullable=False)
    date = Column(Date, default=date.today, index=True, nullable=False)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    target_quantity = Column(Numeric(12, 4), nullable=False)  # Number of packages/units to produce
    status = Column(String(20), default="DRAFT", index=True)  # DRAFT, COMPLETED, CANCELLED
    
    total_cost = Column(Numeric(14, 2), default=Decimal('0.00'))
    unit_cost = Column(Numeric(14, 4), default=Decimal('0.0000'))
    
    destination_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    recipe = relationship("Recipe")
    destination_warehouse = relationship("Warehouse")
    creator = relationship("User")
    journal_entry = relationship("JournalEntry")

    def to_dict(self):
        return {
            "id": self.id,
            "order_number": self.order_number,
            "date": self.date.strftime("%Y-%m-%d") if self.date else None,
            "recipe_id": self.recipe_id,
            "recipe_name": self.recipe.name if self.recipe else "",
            "recipe_name_ar": self.recipe.name_ar if self.recipe else "",
            "finished_item_name": self.recipe.finished_item.name if self.recipe and self.recipe.finished_item else "",
            "target_quantity": float(self.target_quantity or 0),
            "status": self.status,
            "total_cost": float(self.total_cost or 0),
            "unit_cost": float(self.unit_cost or 0),
            "destination_warehouse": self.destination_warehouse.name if self.destination_warehouse else "",
            "journal_entry_number": self.journal_entry.entry_number if self.journal_entry else None,
            "created_by": self.creator.username if self.creator else "System",
            "notes": self.notes
        }
