from sqlmodel import SQLModel, Session, create_engine
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "biztrackr.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


def init_db():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
