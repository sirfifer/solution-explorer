"""SQLAlchemy declarative models (under models/, proving the exclusion inversion)."""
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False)
    name = Column(String)


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    token = Column(String)
