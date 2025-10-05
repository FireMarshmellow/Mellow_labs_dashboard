from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlmodel import select, Session
from ..database import get_session
from ..models import Transfer, Category, Expense
from datetime import date

router = APIRouter()

@router.get("/payroll")
def transfers_list(request: Request, session: Session = Depends(get_session)):
    transfers = session.exec(select(Transfer).order_by(Transfer.date.desc(), Transfer.id.desc())).all()
    return request.app.state.templates.TemplateResponse(
        "transfer_list.html",
        {"request": request, "transfers": transfers},
    )

@router.post("/payroll")
def create_transfer(
    request: Request,
    date: date = Form(...),
    amount_gbp: float = Form(...),
    person: str = Form("Owner"),
    notes: str | None = Form(None),
    session: Session = Depends(get_session),
):
    # Store transfer AND mirror to Expense as Category 'Payroll'
    t = Transfer(date=date, amount_gbp=amount_gbp, person=person, notes=notes)
    session.add(t)
    # ensure Payroll category exists
    payroll = session.exec(select(Category).where(Category.name=="Payroll", Category.kind=="expense")).first()
    if not payroll:
        payroll = Category(name="Payroll", kind="expense")
        session.add(payroll)
        session.commit()
        session.refresh(payroll)
    e = Expense(date=date, total_amount_gbp=amount_gbp, seller=person, category_id=payroll.id, notes=notes)
    session.add(e)
    session.commit()
    return RedirectResponse(url="/payroll", status_code=303)
