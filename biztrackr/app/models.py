from datetime import date, datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Relationship

class IncomeSource(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    notes: Optional[str] = None
    incomes: list["Income"] = Relationship(back_populates="source")

class PaymentProcessor(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    notes: Optional[str] = None
    incomes: list["Income"] = Relationship(back_populates="processor")

class Category(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    kind: str = Field(default="expense", index=True)  # 'expense' or 'income'
    notes: Optional[str] = None
    expenses: list["Expense"] = Relationship(back_populates="category")

class Income(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    date: date
    amount_gbp: float = Field(gt=0)
    notes: Optional[str] = None
    source_id: Optional[int] = Field(default=None, foreign_key="incomesource.id")
    processor_id: Optional[int] = Field(default=None, foreign_key="paymentprocessor.id")
    source: Optional[IncomeSource] = Relationship(back_populates="incomes")
    processor: Optional[PaymentProcessor] = Relationship(back_populates="incomes")

class Expense(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    date: date
    total_amount_gbp: float = Field(gt=0)
    seller: str
    order_number: Optional[str] = None
    notes: Optional[str] = None
    category_id: Optional[int] = Field(default=None, foreign_key="category.id")
    category: Optional[Category] = Relationship(back_populates="expenses")

class Transfer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    date: date
    amount_gbp: float = Field(gt=0)
    person: str = Field(default="Owner")
    notes: Optional[str] = None

class Settings(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    company_name: str = Field(default="My Company")
    youtube_subs: Optional[int] = Field(default=None)
    instagram_followers: Optional[int] = Field(default=None)
    tiktok_followers: Optional[int] = Field(default=None)
    patreon_free: Optional[int] = Field(default=None)
    patreon_paid: Optional[int] = Field(default=None)
    logo_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class SocialMetric(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    platform: str = Field(index=True)           # youtube|instagram|tiktok|patreon
    metric: str = Field(index=True)             # subs|followers|members
    tier: Optional[str] = Field(default=None, index=True)  # free|paid|None
    date: date = Field(index=True)
    value: int = Field(ge=0)
    notes: Optional[str] = None
