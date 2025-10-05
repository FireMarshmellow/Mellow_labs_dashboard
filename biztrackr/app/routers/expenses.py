from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlmodel import select, Session
from ..database import get_session
from ..models import Expense, Category
from datetime import date

router = APIRouter()

@router.get("/expenses")
def expenses_list(request: Request, session: Session = Depends(get_session)):
    expenses = session.exec(select(Expense).order_by(Expense.date.desc(), Expense.id.desc())).all()
    categories = session.exec(select(Category).where(Category.kind=="expense").order_by(Category.name)).all()
    return request.app.state.templates.TemplateResponse(
        "expense_list.html",
        {"request": request, "expenses": expenses, "categories": categories},
    )

@router.post("/expenses")
def create_expense(
    request: Request,
    date: date = Form(...),
    total_amount_gbp: float = Form(...),
    category_id: int | None = Form(None),
    seller: str = Form(...),
    order_number: str | None = Form(None),
    notes: str | None = Form(None),
    session: Session = Depends(get_session),
):
    exp = Expense(date=date, total_amount_gbp=total_amount_gbp, category_id=category_id, seller=seller, order_number=order_number, notes=notes)
    session.add(exp)
    session.commit()
    return RedirectResponse(url="/expenses", status_code=303)

@router.post("/expenses/category")
def create_category(name: str = Form(...), notes: str | None = Form(None), session: Session = Depends(get_session)):
    cat = Category(name=name.strip(), kind="expense", notes=notes)
    session.add(cat)
    session.commit()
    return RedirectResponse(url="/expenses", status_code=303)
