import os
import shutil
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional

from database.db_session import get_db
from database.models import Invoice
from api.auth import get_current_user
from agents.ocr_agent import OCRAgent
from agents.parser_agent import ParserAgent
from agents.validator_agent import ValidatorAgent
from agents.exporter_agent import ExporterAgent
from agents.coral_utils import make_message

# Logging
logger = logging.getLogger("api.invoices")
router = APIRouter(prefix="/invoices", tags=["invoices"])

# Directories
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "data", "input")
EXPORT_DIR = os.path.join(PROJECT_ROOT, "data", "output")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)

# Instantiate agents
ocr = OCRAgent()
parser = ParserAgent()
validator = ValidatorAgent()
exporter = ExporterAgent(export_dir=EXPORT_DIR)


def save_upload_file(upload_file: UploadFile, destination: str):
    with open(destination, "wb") as f:
        shutil.copyfileobj(upload_file.file, f)


@router.post("/upload")
async def upload_invoice(
    file: UploadFile = File(...),
    export_format: str = Form("csv"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    filename = os.path.basename(file.filename or "uploaded_invoice")
    saved_path = os.path.join(UPLOAD_DIR, filename)

    try:
        save_upload_file(file, saved_path)
    except Exception as e:
        logger.exception("Error saving file")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    # OCR
    ocr_msg = make_message(
        msg_type="ocr.extract",
        sender="invoice-endpoint",
        recipient="ocr-agent",
        body={"file_info": {"filename": filename, "path": saved_path}},
    )
    ocr_resp = ocr.handle_coral(ocr_msg)
    invoice_text = ocr_resp.get("body", {}).get("invoice_text")

    if not invoice_text:
        raise HTTPException(status_code=400, detail="OCR extraction failed")

    # Parser
    parser_msg = make_message(
        msg_type="parser.parse_text",
        sender="invoice-endpoint",
        recipient="parser-agent",
        body={"invoice_text": invoice_text},
    )
    parser_resp = parser.handle_coral(parser_msg)
    invoice_data = parser_resp.get("body", {}).get("invoice")

    if not invoice_data:
        raise HTTPException(status_code=400, detail="Parsing failed")

    # Validator
    val_msg = make_message(
        msg_type="validate.invoice",
        sender="invoice-endpoint",
        recipient="validator-agent",
        body={"invoice": invoice_data},
    )
    val_resp = validator.handle_coral(val_msg)
    val_body = val_resp.get("body", {})

    if val_body.get("status") != "PASS":
        raise HTTPException(status_code=400, detail="Validation failed")

    normalized = val_body.get("normalized_data") or invoice_data

    # Export
    export_msg = make_message(
        msg_type="export.invoice",
        sender="invoice-endpoint",
        recipient="exporter-agent",
        body={"invoice": normalized, "format": export_format.lower()},
    )
    export_resp = exporter.handle_coral(export_msg)
    export_body = export_resp.get("body", {})
    export_path = export_body.get("path")

    # Save to database
    invoice = Invoice(
        filename=filename,
        file_path=saved_path,
        export_path=export_path,
        vendor=normalized.get("vendor"),
        invoice_date=normalized.get("date"),
        subtotal=normalized.get("subtotal"),
        tax=normalized.get("tax"),
        total=normalized.get("total"),
        data=normalized,
        owner_id=user.id,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    return JSONResponse({"status": "OK", "invoice_id": invoice.id, "export_path": export_path})


@router.get("/history")
def get_invoice_history(db: Session = Depends(get_db), user=Depends(get_current_user)):
    invoices = db.query(Invoice).filter(Invoice.owner_id == user.id).all()
    return invoices


@router.get("/{invoice_id}")
def get_invoice(invoice_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.owner_id == user.id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.delete("/{invoice_id}")
def delete_invoice(invoice_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.owner_id == user.id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    db.delete(invoice)
    db.commit()
    return {"status": "deleted", "invoice_id": invoice_id}
