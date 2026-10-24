from flask import Flask, request, jsonify
import gspread
from google.oauth2.service_account import Credentials
import os
import json

app = Flask(__name__)

# Google Sheets Setup
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_ID = "1026CotLZWHNTc5nZJyX6wF2LrRO78ao_IBFmkC6Kvo8"

def get_sheet_connection():
    # Load credentials from Render environment variable or local file
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        # Fallback to local file if testing locally
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1

@app.route("/")
def home():
    return "Gym Payment Handler is Live!"

# 1. Validation Endpoint (M-Pesa checks this before accepting payment)
@app.route("/gym-validate", methods=["POST"])
def validate_payment():
    data = request.get_json()
    print("Validation payload received:", data)
    
    # You can add custom validation logic here (e.g., check if member account exists)
    # For now, we accept all incoming transactions
    return jsonify({
        "ResultCode": 0,
        "ResultDesc": "Accepted"
    })

# 2. Confirmation Endpoint (Logs the successful payment to Google Sheets)
@app.route("/gym-webhook", methods=["POST"])
def gym_webhook():
    try:
        data = request.get_json()
        print("Confirmation payload received:", data)

        # Extract transaction fields sent by Safaricom
        trans_id = data.get("TransID", "N/A")
        amount = data.get("TransAmount", "0")
        trans_time = data.get("TransTime", "N/A")
        phone = data.get("MSISDN", "N/A")
        first_name = data.get("FirstName", "Unknown")
        last_name = data.get("LastName", "Unknown")
        full_name = f"{first_name} {last_name}".strip()

        # Connect to Google Sheets and append row
        sheet = get_sheet_connection()
        sheet.append_row([trans_time, full_name, phone, amount, trans_id])

        print(f"Successfully logged payment {trans_id} for {full_name} to Google Sheets!")

        # Safaricom expects a 200 OK response with ResultCode 0
        return jsonify({
            "ResultCode": 0,
            "ResultDesc": "Success"
        })

    except Exception as e:
        print(f"Error processing webhook: {e}")
        return jsonify({
            "ResultCode": 1,
            "ResultDesc": str(e)
        }), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))