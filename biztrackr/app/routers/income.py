from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlmodel import select, Session
from ..database import get_session
from ..models import Income, IncomeSource, PaymentProcessor
from ..schemas import IncomeCreate
from datetime import date

router = APIRouter()

@router.get("/income")
def income_list(request: Request, session: Session = Depends(get_session)):
    incomes = session.exec(select(Income).order_by(Income.date.desc(), Income.id.desc())).all()
    sources = session.exec(select(IncomeSource).order_by(IncomeSource.name)).all()
    processors = session.exec(select(PaymentProcessor).order_by(PaymentProcessor.name)).all()
    return request.app.state.templates.TemplateResponse(
        "income_list.html",
        {"request": request, "incomes": incomes, "sources": sources, "processors": processors},
    )

@router.post("/income")
def create_income(
    request: Request,
    date: date = Form(...),
    amount_gbp: float = Form(...),
    source_id: int | None = Form(None),
    processor_id: int | None = Form(None),
    notes: str | None = Form(None),
    session: Session = Depends(get_session),
):
    income = Income(date=date, amount_gbp=amount_gbp, source_id=source_id, processor_id=processor_id, notes=notes)
    session.add(income)
    session.commit()
    return RedirectResponse(url="/income", status_code=303)

@router.post("/income/source")
def create_source(name: str = Form(...), notes: str | None = Form(None), session: Session = Depends(get_session)):
    src = IncomeSource(name=name.strip(), notes=notes)
    session.add(src)
    session.commit()
    return RedirectResponse(url="/income", status_code=303)

@router.post("/income/processor")
def create_processor(name: str = Form(...), notes: str | None = Form(None), session: Session = Depends(get_session)):
    pp = PaymentProcessor(name=name.strip(), notes=notes)
    session.add(pp)
    session.commit()
    return RedirectResponse(url="/income", status_code=303)
