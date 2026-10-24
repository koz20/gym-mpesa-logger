import os
import json
import logging
from flask import Flask, request, jsonify
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Google Sheets Setup via Environment Variable
def get_google_sheet():
    try:
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        creds_json_str = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if not creds_json_str:
            logging.error("GOOGLE_CREDENTIALS_JSON environment variable is missing!")
            return None

        creds_dict = json.loads(creds_json_str)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
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
    if request.method == 'GET' or not request.is_json:
        return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})

    data = request.get_json(force=True, silent=True) or {}
    logging.info(f"Received M-Pesa Payload: {data}")

    if "TransID" not in data:
        return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})

    try:
        trans_id = data.get('TransID', '')
        trans_amount = data.get('TransAmount', '')
        trans_time = data.get('TransTime', '')
        phone_number = data.get('MSISDN', '')
        first_name = data.get('FirstName', '')
        last_name = data.get('LastName', '')

        payer_name = f"{first_name} {last_name}".strip() or "Unknown"

        sheet = get_google_sheet()
        if sheet:
            sheet.append_row([
                trans_time,
                trans_id,
                phone_number,
                payer_name,
                trans_amount,
                "Success",
                "M-Pesa",
                ""
            ])
            logging.info(f"Payment {trans_id} logged to Google Sheet successfully.")
        else:
            logging.error("Failed to connect to Google Sheet (sheet object is None).")

    except Exception as e:
        logging.error(f"Error processing payment payload: {e}")

    return jsonify({"ResultCode": 0, "ResultDesc": "Success"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)