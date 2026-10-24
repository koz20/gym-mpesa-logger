from flask import Flask, request, jsonify
import gspread
from google.oauth2.service_account import Credentials
import os
import json
from datetime import datetime, timedelta

app = Flask(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_ID = "1026CotLZWHNTc5nZJyX6wF2LrRO78ao_IBFmkC6Kvo8"

# Map payment amounts to Pass Types (Adjust amounts to match your actual gym pricing)
PASS_TYPES = {
    "200": "Daily Pass",
    "500": "Weekly Pass",
    "1500": "Monthly Pass"
}

def get_spreadsheet():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)

def update_frequent_members(spreadsheet):
    """
    Scans payment history, updates Frequent Members tab (3+ visits),
    and removes members inactive for over 30 days.
    """
    try:
        log_sheet = spreadsheet.sheet1
        all_records = log_sheet.get_all_values()
        
        if len(all_records) <= 1:
            return  # No data rows yet

        # Ensure "Frequent Members" worksheet exists
        try:
            freq_sheet = spreadsheet.worksheet("Frequent Members")
        except gspread.exceptions.WorksheetNotFound:
            freq_sheet = spreadsheet.add_worksheet(title="Frequent Members", rows=100, cols=10)
            freq_sheet.append_row(["Member Name", "Phone Number", "Total Visits", "Last Visit Date"])

        # Aggregate visits and last visit date per phone number
        member_stats = {}
        # Skip header row if present
        for row in all_records[1:]:
            if len(row) < 5:
                continue
            trans_time_str, full_name, phone, amount, trans_id = row[0], row[1], row[2], row[3], row[4]
            
            # Parse transaction time
            try:
                visit_dt = datetime.strptime(trans_time_str, "%Y%m%d%H%M%S")
            except ValueError:
                visit_dt = datetime.now()

            if phone not in member_stats:
                member_stats[phone] = {
                    "name": full_name,
                    "visits": 0,
                    "last_visit": visit_dt
                }
            
            member_stats[phone]["visits"] += 1
            if visit_dt > member_stats[phone]["last_visit"]:
                member_stats[phone]["last_visit"] = visit_dt
                member_stats[phone]["name"] = full_name  # Update to latest name

        # Filter active frequent members (3+ visits AND last visit within 30 days)
        now = datetime.now()
        thirty_days_ago = now - timedelta(days=30)
        
        freq_rows = [["Member Name", "Phone Number", "Total Visits", "Last Visit Date"]]
        for phone, stats in member_stats.items():
            if stats["visits"] >= 3 and stats["last_visit"] >= thirty_days_ago:
                freq_rows.append([
                    stats["name"],
                    phone,
                    stats["visits"],
                    stats["last_visit"].strftime("%Y-%m-%d %H:%M")
                ])

        # Refresh Frequent Members sheet content
        freq_sheet.clear()
        freq_sheet.update(range_name="A1", values=freq_rows)
        print("Updated Frequent Members list successfully!")

    except Exception as e:
        print(f"Error updating frequent members: {e}")

@app.route("/")
def home():
    return "Gym Payment Handler is Live!"

@app.route("/gym-validate", methods=["POST"])
def validate_payment():
    return jsonify({
        "ResultCode": 0,
        "ResultDesc": "Accepted"
    })

@app.route("/gym-webhook", methods=["POST"])
def gym_webhook():
    try:
        data = request.get_json()
        print("Confirmation payload received:", data)

        trans_id = data.get("TransID", "N/A")
        amount = str(data.get("TransAmount", "0"))
        trans_time_raw = str(data.get("TransTime", "N/A"))
        phone = data.get("MSISDN", "N/A")
        first_name = data.get("FirstName", "Unknown")
        last_name = data.get("LastName", "Unknown")
        full_name = f"{first_name} {last_name}".strip()

        # Parse date, day of week, and pass type
        try:
            dt = datetime.strptime(trans_time_raw, "%Y%m%d%H%M%S")
            day_of_week = dt.strftime("%A")
            formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            dt = datetime.now()
            day_of_week = dt.strftime("%A")
            formatted_time = trans_time_raw

        pass_type = PASS_TYPES.get(amount, "Session/Daily Fee")

        spreadsheet = get_spreadsheet()
        log_sheet = spreadsheet.sheet1

        # Check for duplicate transaction
        existing_trans_ids = log_sheet.col_values(5)
        if trans_id in existing_trans_ids:
            print(f"Duplicate transaction detected: {trans_id}. Skipping.")
            return jsonify({
                "ResultCode": 0,
                "ResultDesc": "Success - Duplicate Ignored"
            })

        # Append structured row to Main Sheet
        log_sheet.append_row([
            trans_time_raw,
            full_name,
            phone,
            amount,
            trans_id,
            day_of_week,
            pass_type
        ])
        print(f"Logged payment {trans_id} for {full_name} ({pass_type})!")

        # Trigger Frequent Members processing
        update_frequent_members(spreadsheet)

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