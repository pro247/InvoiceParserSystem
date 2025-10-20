# agents/validator_agent.py
from typing import Dict, Any, List, Optional
import jsonschema
from datetime import datetime
from .coral_utils import now_iso


class ValidatorAgent:
    """
    ValidatorAgent: schema + business rules + normalization + date + custom rules
    """

    def __init__(
        self,
        schema: Optional[Dict[str, Any]] = None,
        rules: Optional[Dict[str, Any]] = None,
    ):
        self.id = "validator-agent"
        self.schema = schema or self._default_schema()
        self.rules = rules or {}

    def _default_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": [
                "invoice_number",
                "date",
                "vendor",
                "line_items",
                "subtotal",
                "tax",
                "total",
            ],
            "properties": {
                "invoice_number": {"type": "string"},
                "date": {"type": "string"},
                "vendor": {"type": "string"},
                "line_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["description", "quantity", "unit_price", "total"],
                        "properties": {
                            "description": {"type": "string"},
                            "quantity": {"type": ["number", "integer", "string"]},
                            "unit_price": {"type": ["number", "integer", "string"]},
                            "total": {"type": ["number", "integer", "string"]},
                        },
                        "additionalProperties": True,
                    },
                },
                "subtotal": {"type": ["number", "integer", "string"]},
                "tax": {"type": ["number", "integer", "string"]},
                "total": {"type": ["number", "integer", "string"]},
            },
            "additionalProperties": True,
        }

    def validate_schema(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        validator = jsonschema.Draft7Validator(self.schema)
        errors: List[Dict[str, Any]] = []
        for error in validator.iter_errors(data):
            errors.append(
                {
                    "message": error.message,
                    "path": list(error.path),
                    "validator": error.validator,
                }
            )
        return errors

    def normalize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        normalized = data.copy()
        # Normalize date
        try:
            if "date" in normalized:
                parsed_date = datetime.fromisoformat(
                    str(normalized["date"]).replace("/", "-")
                )
                normalized["date"] = parsed_date.strftime("%Y-%m-%d")
        except Exception:
            pass

        # Trim vendor
        if "vendor" in normalized and isinstance(normalized["vendor"], str):
            normalized["vendor"] = normalized["vendor"].strip()

        # Normalize line items
        if "line_items" in normalized:
            for item in normalized["line_items"]:
                if "quantity" in item:
                    item["quantity"] = float(item["quantity"])
                if "unit_price" in item:
                    item["unit_price"] = float(item["unit_price"])
                if "total" in item:
                    item["total"] = float(item["total"])

        # Normalize totals
        for field in ["subtotal", "tax", "total"]:
            if field in normalized:
                normalized[field] = float(normalized[field])

        return normalized

    def validate_dates(self, data: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        invoice_date = data.get("date")
        if not invoice_date:
            errors.append("Missing invoice date")
            return errors
        try:
            parsed = datetime.fromisoformat(str(invoice_date).replace("/", "-"))
            if parsed.date() > datetime.now().date():
                errors.append(f"Invoice date {invoice_date} is in the future")
        except Exception:
            errors.append(f"Invalid date format: {invoice_date}")
        return errors

    def validate_business_rules(self, data: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        try:
            for i, item in enumerate(data.get("line_items", [])):
                expected_total = float(item["quantity"]) * float(item["unit_price"])
                if float(item["total"]) != expected_total:
                    errors.append(
                        f"Line item {i}: total mismatch (expected {expected_total}, got {item['total']})"
                    )

            subtotal_expected = sum(
                float(item["total"]) for item in data.get("line_items", [])
            )
            if float(data.get("subtotal", 0)) != subtotal_expected:
                errors.append(
                    f"Subtotal mismatch (expected {subtotal_expected}, got {data.get('subtotal')})"
                )

            total_expected = float(data.get("subtotal", 0)) + float(data.get("tax", 0))
            if float(data.get("total", 0)) != total_expected:
                errors.append(
                    f"Total mismatch (expected {total_expected}, got {data.get('total')})"
                )
        except Exception as e:
            errors.append(f"Business rule validation error: {e}")
        return errors

    def validate_custom_rules(self, data: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        if not data.get("vendor"):
            errors.append("Vendor is missing or empty")
        try:
            subtotal = float(data.get("subtotal", 0))
            tax = float(data.get("tax", 0))
            if subtotal > 0:
                tax_rate = tax / subtotal
                if tax_rate > 0.2:
                    errors.append(f"Tax rate too high: {tax_rate:.2%} (max 20%)")
        except Exception:
            errors.append("Error calculating tax rate")
        invoice_number = str(data.get("invoice_number", ""))
        if not invoice_number.startswith("INV-"):
            errors.append(f"Invalid invoice number format: {invoice_number}")
        return errors

    def run_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result = {
            "status": "PASS",
            "valid": True,
            "schema_errors": [],
            "date_errors": [],
            "business_errors": [],
            "custom_errors": [],
            "normalized_data": None,
        }

        normalized = self.normalize(data)
        result["normalized_data"] = normalized

        schema_errors = self.validate_schema(normalized)
        if schema_errors:
            result["status"] = "FAIL"
            result["valid"] = False
            result["schema_errors"] = schema_errors
            return result

        date_errors = self.validate_dates(normalized)
        if date_errors:
            result["status"] = "FAIL"
            result["valid"] = False
            result["date_errors"] = date_errors
            return result

        business_errors = self.validate_business_rules(normalized)
        if business_errors:
            result["status"] = "FAIL"
            result["valid"] = False
            result["business_errors"] = business_errors

        custom_errors = self.validate_custom_rules(normalized)
        if custom_errors:
            result["status"] = "FAIL"
            result["valid"] = False
            result["custom_errors"] = custom_errors

        return result

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

        if intent == "validate.invoice":
            invoice = envelope.get("body", {}).get("invoice")
            if not invoice:
                resp["body"] = {"status": "FAIL", "error": "Missing invoice payload"}
                return resp
            resp["body"] = self.run_data(invoice)
            return resp

        resp["body"] = {"status": "FAIL", "error": f"unsupported intent {intent}"}
        return resp
