from datetime import date, timedelta
from random import randint, random, choice
from sqlmodel import Session, select
from .database import engine, init_db
from .models import IncomeSource, PaymentProcessor, Category, Income, Expense, Transfer, Settings


def seed():
    init_db()
    with Session(engine) as s:
        # Settings
        if not s.exec(select(Settings)).first():
            s.add(Settings(company_name="Mellow Labs", youtube_subs=123456, instagram_followers=9876, tiktok_followers=5432))
        # Lookups
        sources = ["YouTube AdSense", "Sponsorships", "Product Sales", "Affiliate"]
        processors = ["PayPal", "Payoneer", "Direct"]
        exp_cats = ["Tools", "Equipment", "Materials", "Components", "Travel", "Software", "Payroll"]
        for n in sources:
            if not s.exec(select(IncomeSource).where(IncomeSource.name==n)).first():
                s.add(IncomeSource(name=n))
        for n in processors:
            if not s.exec(select(PaymentProcessor).where(PaymentProcessor.name==n)).first():
                s.add(PaymentProcessor(name=n))
        for n in exp_cats:
            if not s.exec(select(Category).where(Category.name==n)).first():
                s.add(Category(name=n, kind="expense"))
        s.commit()
        # sample income/expenses across ~5 years
        start = date.today().replace(month=4, day=6)
        while start.weekday() != 0:
            start -= timedelta(days=1)
        for i in range(5*52):
            d = start - timedelta(weeks=i)
            if random() < 0.6:
                src = choice(s.exec(select(IncomeSource)).all())
                pp = choice(s.exec(select(PaymentProcessor)).all())
                amt = round(100 + random()*900, 2)
                s.add(Income(date=d, amount_gbp=amt, source_id=src.id, processor_id=pp.id, notes="Sample income"))
            if random() < 0.8:
                cat = choice(s.exec(select(Category).where(Category.kind=="expense")).all())
                amt = round(20 + random()*300, 2)
                s.add(Expense(date=d, total_amount_gbp=amt, category_id=cat.id, seller=choice(["Amazon","DFRobot","ToolStation","Air" ]), order_number=str(randint(100000,999999)), notes="Sample expense"))
        s.commit()
        # Some payroll transfers
        for k in range(24):
            d = date.today() - timedelta(weeks=2*k)
            s.add(Transfer(date=d, amount_gbp=500.0, person="Owner", notes="Draw"))
        s.commit()

if __name__ == "__main__":
    seed()
