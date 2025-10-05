from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlmodel import Session, select
from sqlalchemy import text
from datetime import datetime, date

from .database import init_db, get_session
from .models import Settings
from .routers import expenses, income, transfers, settings

# Create FastAPI app
app = FastAPI(title="BizTrackr")

# Setup static files and templates
static_path = Path(__file__).parent / "static"
templates_path = Path(__file__).parent / "templates"

app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
app.state.templates = Jinja2Templates(directory=str(templates_path))

# Include routers
app.include_router(expenses.router)
app.include_router(income.router)
app.include_router(transfers.router)
app.include_router(settings.router)

# Initialize database on startup
@app.on_event("startup")
def on_startup():
    init_db()

# Root route
@app.get("/")
def index(request: Request, session: Session = Depends(get_session)):
    settings = session.exec(select(Settings)).first()
    if not settings:
        settings = Settings()  # Create default settings if none exist
        session.add(settings)
        session.commit()
    
    # Get current fiscal year income grouped by source
    income_fy = session.exec(text("""
        SELECT s.name as label, SUM(i.amount_gbp) as amount
        FROM income i
        LEFT JOIN incomesource s ON i.source_id = s.id
        WHERE i.date >= date('now', 'start of year')
        GROUP BY s.name
        ORDER BY amount DESC
    """)).all()
    
    # Get all-time income grouped by source
    income_all = session.exec(text("""
        SELECT s.name as label, SUM(i.amount_gbp) as amount
        FROM income i
        LEFT JOIN incomesource s ON i.source_id = s.id
        GROUP BY s.name
        ORDER BY amount DESC
    """)).all()
    
    # Get current fiscal year expenses grouped by category
    expense_fy = session.exec(text("""
        SELECT c.name as label, SUM(e.total_amount_gbp) as amount
        FROM expense e
        LEFT JOIN category c ON e.category_id = c.id
        WHERE e.date >= date('now', 'start of year')
        AND c.kind = 'expense'
        GROUP BY c.name
        ORDER BY amount DESC
    """)).all()
    
    # Get all-time expenses grouped by category
    expense_all = session.exec(text("""
        SELECT c.name as label, SUM(e.total_amount_gbp) as amount
        FROM expense e
        LEFT JOIN category c ON e.category_id = c.id
        WHERE c.kind = 'expense'
        GROUP BY c.name
        ORDER BY amount DESC
    """)).all()

    # Get last 12 months of income and expenses for mirror chart
    monthly_data = session.exec(text("""
        WITH RECURSIVE
        months(date) AS (
            SELECT date('now', 'start of month', '-11 months')
            UNION ALL
            SELECT date(date, '+1 month')
            FROM months
            WHERE date < date('now', 'start of month')
        ),
        monthly_income AS (
            SELECT strftime('%Y-%m', date) as month, SUM(amount_gbp) as total
            FROM income
            GROUP BY month
        ),
        monthly_expenses AS (
            SELECT strftime('%Y-%m', date) as month, SUM(total_amount_gbp) as total
            FROM expense
            GROUP BY month
        )
        SELECT 
            strftime('%Y-%m', m.date) as month,
            COALESCE(mi.total, 0) as income,
            COALESCE(me.total, 0) as expenses
        FROM months m
        LEFT JOIN monthly_income mi ON strftime('%Y-%m', m.date) = mi.month
        LEFT JOIN monthly_expenses me ON strftime('%Y-%m', m.date) = me.month
        ORDER BY m.date
    """)).all()
    mirror_data = {
        "labels": [row.month for row in monthly_data],
        "income": [float(row.income) for row in monthly_data],
        "expenses": [float(row.expenses) for row in monthly_data]
    }
    
    pies = {
        "incomeFY": {
            "labels": [row.label or 'Other' for row in income_fy],
            "data": [float(row.amount) for row in income_fy]
        },
        "expenseFY": {
            "labels": [row.label or 'Other' for row in expense_fy],
            "data": [float(row.amount) for row in expense_fy]
        },
        "incomeAll": {
            "labels": [row.label or 'Other' for row in income_all],
            "data": [float(row.amount) for row in income_all]
        },
        "expenseAll": {
            "labels": [row.label or 'Other' for row in expense_all],
            "data": [float(row.amount) for row in expense_all]
        }
    }
    
    return app.state.templates.TemplateResponse(
        "index.html", 
        {
            "request": request, 
            "s": settings,
            "mirror_data": mirror_data,
            "pies": pies
        }
    )