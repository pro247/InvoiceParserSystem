# settings.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # reads .env if present

PROJECT_ROOT = Path(__file__).parent.resolve()
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", DATA_DIR / "input"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", DATA_DIR / "output"))
DB_PATH = os.getenv("DB_PATH", PROJECT_ROOT / "invoice_system.db")

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-this")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

CORAL_SECRET = os.getenv("CORAL_SECRET", "dev-coral-secret")

# Google service account file for gspread (optional)
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON", "")  # path to credentials.json

# ensure dirs exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
