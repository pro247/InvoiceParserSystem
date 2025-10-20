# api/gateway.py
"""
API Gateway for InvoiceParserSystem

- Exposes /process_invoice to accept an uploaded invoice file (pdf/image/txt)
- Orchestrates Coral-style messages to agents (OCR -> Parser -> Validator -> Exporter)
- Returns exporter response (file path or Google Sheets URL) or validation errors

Run with:
    uvicorn api.gateway:app --reload --host 127.0.0.1 --port 8000
"""

import os
import shutil
import logging
from typing import Dict, Any, Optional  # noqa: F401

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi import Request


# coral helper and agents
from agents.coral_utils import make_message
from agents.ocr_agent import OCRAgent
from agents.parser_agent import ParserAgent
from agents.validator_agent import ValidatorAgent
from agents.exporter_agent import ExporterAgent


# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api.gateway")

# Directories
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "data", "input")
EXPORT_DIR = os.path.join(PROJECT_ROOT, "data", "output")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)

app = FastAPI(title="InvoiceParserSystem - API Gateway (Coral v1)")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# Instantiate agents (in-process)
ocr = OCRAgent()
parser = ParserAgent()
validator = ValidatorAgent()
exporter = ExporterAgent(export_dir=EXPORT_DIR)


@app.get("/health")
def health():
    return {"status": "ok"}


def save_upload_file(upload_file: UploadFile, destination: str) -> None:
    """Save an UploadFile to disk (binary-safe)."""
    with open(destination, "wb") as f:
        shutil.copyfileobj(upload_file.file, f)


@app.post("/process_invoice")
async def process_invoice(
    file: UploadFile = File(...),
    export_format: str = Form("csv"),  # csv | xlsx | gsheets
):
    """
    Accepts an uploaded invoice file and runs the full pipeline:
    1. OCR -> returns invoice_text
    2. Parser -> returns structured invoice JSON
    3. Validator -> validates & normalizes
    4. Exporter -> exports to desired format and returns path or URL

    Request: multipart/form-data with fields:
      - file: the invoice file (pdf/image/txt)
      - export_format: csv/xlsx/gsheets (optional, default csv)
    """
    # 0. Basic validation
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")

    filename = os.path.basename(file.filename or "uploaded_invoice")
    saved_path = os.path.join(UPLOAD_DIR, filename)

    # 1. Save uploaded file to disk
    try:
        save_upload_file(file, saved_path)
    except Exception as e:
        logger.exception("Failed to save upload")
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")

    logger.info("Saved uploaded file: %s", saved_path)

    # 2. OCR agent (Coral message)
    ocr_msg = make_message(
        msg_type="ocr.extract",
        sender="api-gateway",
        recipient="ocr-agent",
        body={"file_info": {"filename": filename, "path": saved_path}},
    )
    ocr_resp = ocr.handle_coral(ocr_msg)
    logger.info("OCR response: %s", ocr_resp)

    invoice_text = ocr_resp.get("body", {}).get("invoice_text")
    if not invoice_text:
        return JSONResponse(
            {"status": "FAIL", "stage": "ocr", "error": "OCR failed or returned empty text"},
            status_code=400,
        )

    # 3. Parser agent
    parser_msg = make_message(
        msg_type="parser.parse_text",
        sender="api-gateway",
        recipient="parser-agent",
        body={"invoice_text": invoice_text},
    )
    parser_resp = parser.handle_coral(parser_msg)
    logger.info("Parser response: %s", parser_resp)

    invoice = parser_resp.get("body", {}).get("invoice")
    if not invoice:
        return JSONResponse(
            {"status": "FAIL", "stage": "parser", "error": "Parsing failed or returned no invoice"},
            status_code=400,
        )

    # 4. Validator agent
    val_msg = make_message(
        msg_type="validate.invoice",
        sender="api-gateway",
        recipient="validator-agent",
        body={"invoice": invoice},
    )
    val_resp = validator.handle_coral(val_msg)
    logger.info("Validator response: %s", val_resp)

    val_body = val_resp.get("body", {})
    if val_body.get("status") != "PASS" or not val_body.get("valid", False):
        # Return validation details to the caller (do not proceed to export)
        return JSONResponse({"status": "FAIL", "stage": "validate", "validation": val_body}, status_code=400)

    # 5. Exporter agent (use normalized_data from validator)
    normalized = val_body.get("normalized_data") or invoice
    export_msg = make_message(
        msg_type="export.invoice",
        sender="api-gateway",
        recipient="exporter-agent",
        body={"invoice": normalized, "format": (export_format or "csv").lower()},
    )
    export_resp = exporter.handle_coral(export_msg)
    logger.info("Exporter response: %s", export_resp)

    export_body = export_resp.get("body", {})
    if export_body.get("status") != "PASS":
        return JSONResponse({"status": "FAIL", "stage": "export", "error": export_body.get("error")}, status_code=500)

    # 6. Success
    result = {"status": "OK", "export": export_body}
    return JSONResponse(result)
