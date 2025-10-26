# api/invoice.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.db_session import SessionLocal
from models import Invoice
from api.auth import get_current_user

router = APIRouter(prefix="/invoices", tags=["invoices"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/", summary="Get all invoices for current user")
def list_invoices(db: Session = Depends(get_db), user=Depends(get_current_user)):
    invoices = db.query(Invoice).filter(Invoice.owner_id == user.id).all()
    return invoices


@router.get("/{invoice_id}", summary="Get invoice details")
def get_invoice(invoice_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.owner_id == user.id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice
