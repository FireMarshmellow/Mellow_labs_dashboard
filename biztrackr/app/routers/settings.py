from fastapi import APIRouter, Depends, Request, Form, UploadFile
from fastapi.responses import RedirectResponse
from sqlmodel import select, Session
from ..database import get_session
from ..models import Settings
from pathlib import Path

router = APIRouter()

@router.get("/settings")
def settings_view(request: Request, session: Session = Depends(get_session)):
    s = session.exec(select(Settings)).first()
    return request.app.state.templates.TemplateResponse("settings.html", {"request": request, "s": s})

@router.post("/settings")
def settings_update(
    request: Request,
    company_name: str = Form(None),
    youtube_subs: int | None = Form(None),
    instagram_followers: int | None = Form(None),
    tiktok_followers: int | None = Form(None),
    logo: UploadFile | None = None,
    session: Session = Depends(get_session),
):
    s = session.exec(select(Settings)).first()
    if not s:
        s = Settings()
        session.add(s)
    s.company_name = company_name or s.company_name
    s.youtube_subs = youtube_subs
    s.instagram_followers = instagram_followers
    s.tiktok_followers = tiktok_followers
    # save logo if provided
    if logo and logo.filename:
        logos_dir = Path(__file__).resolve().parent / "static" / "logos"
        logos_dir.mkdir(parents=True, exist_ok=True)
        dest = logos_dir / logo.filename
        dest.write_bytes(logo.file.read())
        s.logo_path = "/static/logos/" + logo.filename
    session.commit()
    return RedirectResponse(url="/settings", status_code=303)
