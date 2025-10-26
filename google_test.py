# google_test.py
import os
from google.oauth2.service_account import Credentials
import gspread
from googleapiclient.discovery import build

# path to your downloaded JSON key
SERVICE_FILE = os.getenv("GOOGLE_CREDS_JSON", "service_account.json")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

creds = Credentials.from_service_account_file(SERVICE_FILE, scopes=SCOPES)
gc = gspread.authorize(creds)

# 1) Create new spreadsheet
title = "Invoice_Test_Sheet"
sh = gc.create(title)

# 2) Optionally share it with a human Google account (replace email)
# If you want to share with your personal Google account so you can open it in browser:
human_email = "your.email@gmail.com"  # <-- change this
sh.share(human_email, perm_type="user", role="writer")

# 3) Write data
worksheet = sh.sheet1
worksheet.update("A1", [["Description", "Qty", "Unit", "Total"]])
worksheet.append_row(["Widget", 1, 50.0, 50.0])

print("Created sheet:", sh.url)

# 4) As an alternative, set "anyone with link" permission using Drive API:
drive_service = build("drive", "v3", credentials=creds)
perm = {"type": "anyone", "role": "writer"}  # or "reader"
drive_service.permissions().create(fileId=sh.id, body=perm).execute()
print("Sheet URL (anyone):", f"https://docs.google.com/spreadsheets/d/{sh.id}")
