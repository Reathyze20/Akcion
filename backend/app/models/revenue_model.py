"""
Analytikovy modely tržeb — viz migrations/add_analyst_revenue_models.sql pro
plné odůvodnění. `AnalystRevenueModel` je dokument (kdo, odkud, kdy),
`AnalystRevenueModelLine` jsou jeho řádky (kategorie, položka, období, číslo).
"""
from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from .base import Base

CONFIDENCE_LOCKED = "LOCKED"
CONFIDENCE_ESTIMATE = "ESTIMATE"
CONFIDENCE_VALUES = (CONFIDENCE_LOCKED, CONFIDENCE_ESTIMATE)


class AnalystRevenueModel(Base):
    __tablename__ = "analyst_revenue_models"

    id = Column(Integer, primary_key=True)
    ticker = Column(String(20), nullable=False, index=True)
    company_name = Column(String(200), nullable=True)
    source_name = Column(String(100), nullable=False, default="Mark Gomes")
    model_name = Column(String(200), nullable=False)
    document_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    lines = relationship(
        "AnalystRevenueModelLine",
        back_populates="model",
        cascade="all, delete-orphan",
        order_by="AnalystRevenueModelLine.id",
    )


class AnalystRevenueModelLine(Base):
    __tablename__ = "analyst_revenue_model_lines"
    __table_args__ = (
        CheckConstraint(
            "amount IS NOT NULL OR (quantity IS NOT NULL AND price_per_unit IS NOT NULL)",
            name="amount_or_unit_math",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence IN ('LOCKED', 'ESTIMATE')",
            name="confidence_known_values",
        ),
    )

    id = Column(Integer, primary_key=True)
    model_id = Column(
        Integer, ForeignKey("analyst_revenue_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category = Column(String(150), nullable=False)
    item_name = Column(String(200), nullable=False)
    period_label = Column(String(20), nullable=False)
    quantity = Column(Numeric(18, 2), nullable=True)
    price_per_unit = Column(Numeric(18, 4), nullable=True)
    amount = Column(Numeric(18, 2), nullable=True)
    currency = Column(String(5), nullable=False, default="USD")
    confidence = Column(String(10), nullable=True)
    note = Column(Text, nullable=True)

    model = relationship("AnalystRevenueModel", back_populates="lines")

    def resolved_amount(self) -> float | None:
        """Částka z dokumentu, nebo kusy × cena, když je jen tohle."""
        if self.amount is not None:
            return float(self.amount)
        if self.quantity is not None and self.price_per_unit is not None:
            return float(self.quantity) * float(self.price_per_unit)
        return None
