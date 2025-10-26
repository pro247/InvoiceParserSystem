# api/gateway.py
from database.db_session import SessionLocal
from models import Invoice

import os
import shutil
import logging
import json
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from typing import Dict
from fastapi.middleware.cors import CORSMiddleware

from models import Invoice, Export
from settings import UPLOAD_DIR, OUTPUT_DIR

from database.db_session import engine
from database.models import Base

from api.invoice_routes import router as invoice_router


# agents and coral
from agents.coral_utils import make_message
from agents.ocr_agent import OCRAgent
from agents.parser_agent import ParserAgent
from agents.validator_agent import ValidatorAgent
from agents.exporter_agent import ExporterAgent

# auth
from api.auth import router as auth_router, get_current_user

# Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api.gateway")

app = FastAPI(title="InvoiceParserSystem - API Gateway (Auth + Coral)")
app.include_router(auth_router, prefix="/auth")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for testing, later limit to ["http://127.0.0.1:8000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)
app.include_router(auth_router)
app.include_router(invoice_router)

# Instantiate agents
ocr = OCRAgent()
parser = ParserAgent()
validator = ValidatorAgent()
exporter = ExporterAgent(export_dir=str(OUTPUT_DIR))

# ensure directories
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/health")
def health():
    return {"status": "ok"}


def save_upload_file(upload_file: UploadFile, destination: str) -> None:
    with open(destination, "wb") as f:
        shutil.copyfileobj(upload_file.file, f)


@app.post("/process_invoice")
async def process_invoice(
    file: UploadFile = File(...),
    export_format: str = Form("csv"),
    current_user=Depends(get_current_user),
):
    """
    Protected endpoint: user must be authenticated (JWT).
    """
    # save file
    filename = os.path.basename(file.filename or "uploaded_invoice")
    saved_path = os.path.join(UPLOAD_DIR, f"{current_user.id}_{filename}")
    save_upload_file(file, saved_path)
    logger.info("Saved uploaded file: %s", saved_path)

    # OCR
    ocr_msg = make_message(
        "ocr.extract", sender="api-gateway", recipient="ocr-agent", body={"file_info": {"filename": filename, "path": saved_path}}
    )
    ocr_resp = ocr.handle_coral(ocr_msg)
    invoice_text = ocr_resp.get("body", {}).get("invoice_text")
    if not invoice_text:
        raise HTTPException(status_code=400, detail="OCR failed")

    # Parser
    parser_msg = make_message("parser.parse_text", sender="api-gateway", recipient="parser-agent", body={"invoice_text": invoice_text})
    parser_resp = parser.handle_coral(parser_msg)
    invoice = parser_resp.get("body", {}).get("invoice")
    if not invoice:
        raise HTTPException(status_code=400, detail="Parsing failed")

    # Validator
    val_msg = make_message("validate.invoice", sender="api-gateway", recipient="validator-agent", body={"invoice": invoice})
    val_resp = validator.handle_coral(val_msg)
    val_body = val_resp.get("body", {})
    if val_body.get("status") != "PASS" or not val_body.get("valid", False):
        return JSONResponse({"status": "FAIL", "validation": val_body}, status_code=400)

    normalized = val_body.get("normalized_data") or invoice

    # Save invoice record to DB
    db = SessionLocal()
    try:
        inv = Invoice(
            user_id=current_user.id,
            invoice_number=normalized.get("invoice_number"),
            vendor=normalized.get("vendor"),
            date=normalized.get("date"),
            raw_file=saved_path,
            normalized_json=json.dumps(normalized),
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    # Export
    export_msg = make_message(
        "export.invoice",
        sender="api-gateway",
        recipient="exporter-agent",
        body={"invoice": normalized, "format": (export_format or "csv").lower(), "invoice_id": inv.id},
    )
    export_resp = exporter.handle_coral(export_msg)
    export_body = export_resp.get("body", {})

    # If exporter succeeded, record export in DB
    if export_body.get("status") == "PASS":
        try:
            ex = Export(invoice_id=inv.id, export_format=export_body.get("format", export_format), export_path=export_body.get("file"))
            db.add(ex)
            db.commit()
            db.refresh(ex)
        except Exception as e:
            db.rollback()
            logger.exception("Failed to record export: %s", e)
    else:
        # exporter failed
        return JSONResponse({"status": "FAIL", "export": export_body}, status_code=500)
    db.close()

    return JSONResponse({"status": "OK", "export": export_body})

    # 6. Save to database
    db = SessionLocal()
    try:
        inv_record = Invoice(
            filename=filename,
            total=normalized.get("total"),
            vendor=normalized.get("vendor"),
            date=normalized.get("date"),
            export_path=export_body.get("file"),
        )
        db.add(inv_record)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to save invoice record: {e}")
        db.rollback()
    finally:
        db.close()

    # 7. Success
    result = {"status": "OK", "export": export_body}
    return JSONResponse(result)


@app.get("/invoices")
def list_invoices(current_user=Depends(get_current_user)):
    db = SessionLocal()
    rows = db.query(Invoice).filter(Invoice.user_id == current_user.id).order_by(Invoice.created_at.desc()).all()
    results = []
    for r in rows:
        latest_export = r.exports[-1] if r.exports else None
        results.append(
            {
                "invoice_id": r.id,
                "invoice_number": r.invoice_number,
                "vendor": r.vendor,
                "date": r.date,
                "raw_file": r.raw_file,
                "normalized": r.normalized_json,
                "export": {
                    "id": latest_export.id if latest_export else None,
                    "format": latest_export.export_format if latest_export else None,
                    "path": latest_export.export_path if latest_export else None,
                },
                "created_at": str(r.created_at),
            }
        )
    db.close()
    return {"invoices": results}


@app.get("/download/{export_id}")
def download_export(export_id: int, current_user=Depends(get_current_user)):
    db = SessionLocal()
    ex = db.query(Export).filter(Export.id == export_id).first()
    if not ex:
        raise HTTPException(status_code=404, detail="Export not found")
    inv = db.query(Invoice).filter(Invoice.id == ex.invoice_id).first()
    if inv.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.close()

    if ex.export_format == "gsheets":
        # return sheets URL
        return {"url": ex.export_path}
    # else local file
    if not ex.export_path or not os.path.exists(ex.export_path):
        raise HTTPException(status_code=404, detail="Export file not found")
    return FileResponse(path=ex.export_path, filename=os.path.basename(ex.export_path), media_type="application/octet-stream")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user=Depends(get_current_user)):
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})
