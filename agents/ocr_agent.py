# agents/ocr_agent.py
from typing import Dict, Any
from .coral_utils import now_iso


class OCRAgent:
    """
    OCRAgent (simulated)
    - Handles 'ocr.extract' messages
    - Returns a simple 'invoice_text' in the body for downstream parsing
    """

    def __init__(self):
        self.id = "ocr-agent"

    def handle_coral(self, envelope: Dict[str, Any]) -> Dict[str, Any]:
        intent = envelope.get("type")
        sender = envelope.get("from")
        resp = {
            "id": f"resp-{envelope.get('id')}",
            "type": f"{intent}.response",
            "from": self.id,
            "to": sender,
            "timestamp": now_iso(),
            "body": {},
        }

        if intent == "ocr.extract":
            # Expect body.file_info = {"filename": ..., "content": <optional raw bytes or text>}
            file_info = envelope.get("body", {}).get("file_info", {})
            filename = file_info.get("filename", "unknown")
            # *** Replace this simulated OCR with real OCR (pytesseract) in production ***
            simulated_text = (
                f"INV-1001\nDate: 2025-09-18\nVendor: ACME Corp\n"
                "1 x Widget @ 50.00 = 50.00\nSubtotal: 50.00\nTax: 5.00\nTotal: 55.00"
            )
            resp["body"] = {"invoice_text": simulated_text, "source_file": filename}
            return resp

        resp["body"] = {"status": "FAIL", "error": f"unsupported intent {intent}"}
        return resp
