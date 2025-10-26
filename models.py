# models.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(150), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(256), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    invoices = relationship("Invoice", back_populates="user")


class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    invoice_number = Column(String(100), index=True, nullable=True)
    vendor = Column(String(255), nullable=True)
    date = Column(String(50), nullable=True)
    raw_file = Column(String(1024), nullable=False)  # path to uploaded file
    normalized_json = Column(Text, nullable=True)  # JSON string of normalized invoice
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="invoices")
    exports = relationship("Export", back_populates="invoice")


class Export(Base):
    __tablename__ = "exports"
    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    export_format = Column(String(20), nullable=False)  # csv / xlsx / gsheets
    export_path = Column(String(1024), nullable=True)  # local path or gsheets url
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    invoice = relationship("Invoice", back_populates="exports")
