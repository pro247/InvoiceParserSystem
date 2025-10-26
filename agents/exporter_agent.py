# agents/exporter_agent.py
import os
import json
import pandas as pd
import gspread
from typing import Dict, Any
from .coral_utils import now_iso
from settings import OUTPUT_DIR, GOOGLE_CREDS_JSON
from oauth2client.service_account import ServiceAccountCredentials

# Optional Google Sheets setup
USE_GSHEETS = bool(GOOGLE_CREDS_JSON)
GSCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]


class ExporterAgent:
    def __init__(self, export_dir: str = None):
        self.id = "exporter-agent"
        self.export_dir = export_dir or str(OUTPUT_DIR)
        os.makedirs(self.export_dir, exist_ok=True)
        self.gc = None
        if USE_GSHEETS:
            try:
                creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDS_JSON, GSCOPE)
                self.gc = gspread.authorize(creds)
            except Exception as e:
                # keep going without sheets
                print("Failed to init gspread:", e)
                self.gc = None

    def export_csv(self, invoice: Dict[str, Any], filename: str) -> str:
        path = os.path.join(self.export_dir, f"{filename}.csv")
        df = pd.DataFrame(invoice.get("line_items", []))
        df.to_csv(path, index=False)
        return path

    def export_xlsx(self, invoice: Dict[str, Any], filename: str) -> str:
        path = os.path.join(self.export_dir, f"{filename}.xlsx")
        df = pd.DataFrame(invoice.get("line_items", []))
        with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
            df.to_excel(writer, sheet_name="LineItems", index=False)
            # write a simple summary sheet
            workbook = writer.book
            try:
                summary_sheet = workbook.add_worksheet("Summary")  # xlsxwriter method
                # xlsxwriter workbook API uses worksheet.write(row, col, value)
                summary_sheet.write(0, 0, "Invoice Number")
                summary_sheet.write(0, 1, invoice.get("invoice_number"))
                summary_sheet.write(1, 0, "Vendor")
                summary_sheet.write(1, 1, invoice.get("vendor"))
                summary_sheet.write(2, 0, "Date")
                summary_sheet.write(2, 1, invoice.get("date"))
                summary_sheet.write(3, 0, "Subtotal")
                summary_sheet.write(3, 1, invoice.get("subtotal"))
                summary_sheet.write(4, 0, "Tax")
                summary_sheet.write(4, 1, invoice.get("tax"))
                summary_sheet.write(5, 0, "Total")
                summary_sheet.write(5, 1, invoice.get("total"))
            except Exception:
                # ignore if engine doesn't support this in type hints
                pass
        return path

    def export_gsheets(self, invoice: Dict[str, Any], filename: str) -> str:
        if not self.gc:
            raise RuntimeError("Google Sheets not configured")
        # create a new spreadsheet
        sh = self.gc.create(f"Invoice-{filename}-{now_iso()}")
        # share (optional) - by default service account owns it; to view in web you may need to share with your user
        # write line items
        ws = sh.sheet1
        # header row
        headers = ["description", "quantity", "unit_price", "total"]
        ws.append_row(headers)
        for it in invoice.get("line_items", []):
            ws.append_row([it.get("description"), it.get("quantity"), it.get("unit_price"), it.get("total")])
        # add summary in later sheet
        try:
            sh.add_worksheet(title="Summary", rows=10, cols=3)
            s = sh.worksheet("Summary")
            s.update("A1", "Invoice Number")
            s.update("B1", invoice.get("invoice_number"))
            s.update("A2", "Vendor")
            s.update("B2", invoice.get("vendor"))
            s.update("A3", "Date")
            s.update("B3", invoice.get("date"))
        except Exception:
            pass
        # return the web url
        return sh.url

    def handle_coral(self, envelope: Dict[str, Any]) -> Dict[str, Any]:
        intent = envelope.get("type")
        sender = envelope.get("from")
        body = envelope.get("body", {})
        resp = {
            "id": f"resp-{envelope.get('id')}",
            "type": f"{intent}.response",
            "from": self.id,
            "to": sender,
            "timestamp": now_iso(),
            "body": {},
        }

        if intent == "export.invoice":
            invoice = body.get("invoice")
            fmt = (body.get("format") or "csv").lower()
            invoice_id = body.get("invoice_id")
            if not invoice:
                resp["body"] = {"status": "FAIL", "error": "Missing invoice payload"}
                return resp
            filename = invoice.get("invoice_number") or f"invoice_{invoice_id or 'unknown'}"
            filename = filename.replace(" ", "_")
            try:
                if fmt == "csv":
                    path = self.export_csv(invoice, filename)
                    resp["body"] = {"status": "PASS", "file": path, "format": "csv"}
                elif fmt in ("xls", "xlsx", "excel"):
                    path = self.export_xlsx(invoice, filename)
                    resp["body"] = {"status": "PASS", "file": path, "format": "xlsx"}
                elif fmt in ("gsheets", "sheets", "sheet"):
                    url = self.export_gsheets(invoice, filename)
                    resp["body"] = {"status": "PASS", "file": url, "format": "gsheets"}
                else:
                    resp["body"] = {"status": "FAIL", "error": f"Unsupported format {fmt}"}
            except Exception as e:
                resp["body"] = {"status": "FAIL", "error": str(e)}
            return resp

        resp["body"] = {"status": "FAIL", "error": f"unsupported intent {intent}"}
        return resp
