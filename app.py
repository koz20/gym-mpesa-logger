import os
import logging
from flask import Flask, request, jsonify
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Google Sheets Setup
def get_google_sheet():
    try:
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds_file = 'credentials.json'
        if os.path.exists(creds_file):
            creds = Credentials.from_service_account_file(creds_file, scopes=scope)
            client = gspread.authorize(creds)
            sheet_id = "1026CotLZWHNTc5nZJyX6wF2LrRO78ao_IBFmkC6Kvo8"
            return client.open_by_key(sheet_id).sheet1
    except Exception as e:
        logging.error(f"Google Sheets connection error: {e}")
    return None

@app.route('/', methods=['GET'])
def home():
    return "Gym Payment Handler is Live!", 200

@app.route('/mpesa-webhook', methods=['GET', 'POST'], strict_slashes=False)
def mpesa_webhook():
    # Handle validation pings or non-JSON requests
    if request.method == 'GET' or not request.is_json:
        return jsonify({
            "ResultCode": 0,
            "ResultDesc": "Accepted"
        })

    data = request.get_json(force=True, silent=True) or {}
    logging.info(f"Received M-Pesa Payload: {data}")

    # If payload lacks transaction ID, treat as validation ping
    if "TransID" not in data:
        return jsonify({
            "ResultCode": 0,
            "ResultDesc": "Accepted"
        })

    # Confirmation Payload - Log to Google Sheet
    try:
        trans_id = data.get('TransID', '')
        trans_amount = data.get('TransAmount', '')
        trans_time = data.get('TransTime', '')
        phone_number = data.get('MSISDN', '')
        first_name = data.get('FirstName', '')
        last_name = data.get('LastName', '')
        account_number = data.get('BillRefNumber', '')

        payer_name = f"{first_name} {last_name}".strip() or "Unknown"

        sheet = get_google_sheet()
        if sheet:
            sheet.append_row([
                trans_time,
                trans_id,
                trans_amount,
                payer_name,
                phone_number,
                account_number
            ])
            logging.info(f"Payment {trans_id} logged to Google Sheet successfully.")
        else:
            logging.error("Failed to connect to Google Sheet.")

    except Exception as e:
        logging.error(f"Error processing payment payload: {e}")

    return jsonify({
        "ResultCode": 0,
        "ResultDesc": "Success"
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)