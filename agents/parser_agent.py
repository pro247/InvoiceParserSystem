# agents/parser_agent.py
from typing import Dict, Any
import re
from .coral_utils import now_iso


class ParserAgent:
    """
    ParserAgent (simple rule-based parser)
    - Handles 'parser.parse_text' messages
    - Produces a structured invoice JSON in body.invoice
    """

    def __init__(self):
        self.id = "parser-agent"

    def _basic_parse(self, text: str) -> Dict[str, Any]:
        # Very simple extraction for demo purposes — replace with robust logic or ML model
        invoice_number = None
        m = re.search(r"(INV[-\s]?\d+)", text, re.IGNORECASE)
        if m:
            invoice_number = m.group(1).upper()
        else:
            invoice_number = "INV-UNKNOWN"

        # date
        m = re.search(r"Date[:\s]*([0-9]{4}[-/][0-9]{2}[-/][0-9]{2})", text)
        date = m.group(1) if m else "1970-01-01"

        # vendor
        m = re.search(r"Vendor[:\s]*(.+)", text)
        vendor = m.group(1).strip() if m else "Unknown Vendor"

        # items & totals: naive extraction
        # find lines with pattern: qty x desc @ unit = total or description lines
        line_items = []
        for line in text.splitlines():
            m = re.search(r"(\d+)\s*x\s*(.+?)@\s*([\d.,]+)\s*=\s*([\d.,]+)", line)
            if m:
                qty = float(m.group(1))
                desc = m.group(2).strip()
                unit = float(m.group(3).replace(",", ""))
                total = float(m.group(4).replace(",", ""))
                line_items.append(
                    {
                        "description": desc,
                        "quantity": qty,
                        "unit_price": unit,
                        "total": total,
                    }
                )

        # fallback simple item if none found
        if not line_items:
            line_items = [
                {
                    "description": "Service",
                    "quantity": 1,
                    "unit_price": 50.0,
                    "total": 50.0,
                }
            ]

        # subtotal/tax/total
        m = re.search(r"Subtotal[:\s]*([\d.,]+)", text)
        subtotal = (
            float(m.group(1).replace(",", ""))
            if m
            else sum(i["total"] for i in line_items)
        )
        m = re.search(r"Tax[:\s]*([\d.,]+)", text)
        tax = float(m.group(1).replace(",", "")) if m else round(subtotal * 0.1, 2)
        m = re.search(r"Total[:\s]*([\d.,]+)", text)
        total = float(m.group(1).replace(",", "")) if m else subtotal + tax

        invoice = {
            "invoice_number": invoice_number,
            "date": date,
            "vendor": vendor,
            "line_items": line_items,
            "subtotal": subtotal,
            "tax": tax,
            "total": total,
        }
        return invoice

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

        if intent == "parser.parse_text":
            text = envelope.get("body", {}).get("invoice_text", "")
            invoice = self._basic_parse(text)
            resp["body"] = {"invoice": invoice}
            return resp

        resp["body"] = {"status": "FAIL", "error": f"unsupported intent {intent}"}
        return resp
