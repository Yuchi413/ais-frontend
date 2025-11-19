# models/blacklist_model.py
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import create_engine
from datetime import datetime
import os

DB_PATH = os.path.join(os.getcwd(), "assets", "blacklist.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class BlacklistShip(Base):
    __tablename__ = "blacklist_ships"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # 船名
    note = Column(String, nullable=True)   # 備註
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)
