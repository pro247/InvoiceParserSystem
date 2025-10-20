# agents/exporter_agent.py
import os
import pandas as pd
from typing import Dict, Any
from .coral_utils import now_iso


class ExporterAgent:
    """
    ExporterAgent
    - Handles 'export.invoice' messages
    - Supports CSV and XLSX (Google Sheets placeholder)
    """

    def __init__(self, export_dir: str = "data/output"):
        self.id = "exporter-agent"
        self.export_dir = export_dir
        os.makedirs(export_dir, exist_ok=True)

    def export_csv(self, invoice: Dict[str, Any], filename: str) -> str:
        path = os.path.join(self.export_dir, f"{filename}.csv")
        df = pd.DataFrame(invoice.get("line_items", []))
        df.to_csv(path, index=False)
        return path

    def export_xlsx(self, invoice: Dict[str, Any], filename: str) -> str:
        path = os.path.join(self.export_dir, f"{filename}.xlsx")
        df = pd.DataFrame(invoice.get("line_items", []))
        with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
            df.to_excel(writer, sheet_name="Line Items", index=False)
            workbook = writer.book
            try:
                summary = workbook.add_worksheet("Summary")  # type: ignore[attr-defined]
                summary.write(0, 0, "Invoice Number")
                summary.write(0, 1, invoice.get("invoice_number"))
                summary.write(1, 0, "Vendor")
                summary.write(1, 1, invoice.get("vendor"))
                summary.write(2, 0, "Date")
                summary.write(2, 1, invoice.get("date"))
                summary.write(3, 0, "Subtotal")
                summary.write(3, 1, invoice.get("subtotal"))
                summary.write(4, 0, "Tax")
                summary.write(4, 1, invoice.get("tax"))
                summary.write(5, 0, "Total")
                summary.write(5, 1, invoice.get("total"))
            except Exception:
                # if workbook operations fail, ignore summary writing
                pass
        return path

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
            if not invoice:
                resp["body"] = {"status": "FAIL", "error": "Missing invoice payload"}
                return resp
            filename = invoice.get("invoice_number", "invoice").replace(" ", "_")
            try:
                if fmt == "csv":
                    file_path = self.export_csv(invoice, filename)
                    resp["body"] = {"status": "PASS", "file": file_path}
                elif fmt in ("xls", "xlsx", "excel"):
                    file_path = self.export_xlsx(invoice, filename)
                    resp["body"] = {"status": "PASS", "file": file_path}
                else:
                    resp["body"] = {
                        "status": "FAIL",
                        "error": f"Unsupported format {fmt}",
                    }
            except Exception as e:
                resp["body"] = {"status": "FAIL", "error": str(e)}
            return resp

        resp["body"] = {"status": "FAIL", "error": f"unsupported intent {intent}"}
        return resp
