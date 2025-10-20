# agents/coral_utils.py
import json
import uuid
import hmac
import hashlib
from datetime import datetime
from typing import Optional
from typing import Dict, Any


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def make_message(
    msg_type: str,
    sender: str,
    recipient: str,
    body: Dict[str, Any],
    msg_id: Optional[str] = None,
    metadata: Dict[str, Any] = {},
) -> Dict[str, Any]:
    return {
        "id": msg_id or str(uuid.uuid4()),
        "type": msg_type,
        "from": sender,
        "to": recipient,
        "timestamp": now_iso(),
        "body": body or {},
        "metadata": metadata or {},
    }


def _serialize_for_signing(message: Dict[str, Any]) -> bytes:
    # deterministic JSON for signature
    return json.dumps(message, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_message(message: Dict[str, Any], secret: str) -> str:
    payload = _serialize_for_signing(message)
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_signature(message: Dict[str, Any], signature: str, secret: str) -> bool:
    expected = sign_message(message, secret)
    return hmac.compare_digest(expected, signature)
