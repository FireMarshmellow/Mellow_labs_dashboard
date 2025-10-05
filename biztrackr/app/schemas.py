from datetime import date
from typing import Optional
from pydantic import BaseModel

class IncomeCreate(BaseModel):
    date: date
    amount_gbp: float
    source_id: Optional[int]
    processor_id: Optional[int]
    notes: Optional[str] = None

class ExpenseCreate(BaseModel):
    date: date
    total_amount_gbp: float
    seller: str
    order_number: Optional[str] = None
    category_id: Optional[int]
    notes: Optional[str] = None

class TransferCreate(BaseModel):
    date: date
    amount_gbp: float
    person: str = "Owner"
    notes: Optional[str] = None

class SettingsUpdate(BaseModel):
    company_name: Optional[str] = None
    youtube_subs: Optional[int] = None
    instagram_followers: Optional[int] = None
    tiktok_followers: Optional[int] = None
