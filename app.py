import os  
import re  
import json  
import io  
import logging
from datetime import datetime  
import pytz  
from flask import Flask, request, jsonify, send_file, render_template_string
from flask_sqlalchemy import SQLAlchemy  
import gspread  
from google.oauth2.service_account import Credentials  

# ReportLab Imports for PDF Generation  
from reportlab.lib.pagesizes import letter  
from reportlab.lib import colors  
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle  
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)  

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL", "sqlite:////tmp/gym_payments.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

APP_BASE_URL = os.getenv("APP_BASE_URL", "https://gym-mpesa-logger.onrender.com")  
NAIROBI_TZ = pytz.timezone("Africa/Nairobi")  

GYM_SHORTCODE = "174379"
GYM_SHEET_ID = os.getenv("GYM_SHEET_ID", "1026CotLZWHNTc5nZJyX6wF2LrRO78ao_IBFmkC6Kvo8")
GYM_NAME = os.getenv("GYM_NAME", "FITNESS GYM")

# ==========================================  
# DATABASE MODEL (Mirrors Kinkam's safety net)
# ==========================================  
class GymPaymentRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.String(30), nullable=False)
    ref_id = db.Column(db.String(50), unique=True, nullable=False) 
    phone_number = db.Column(db.String(20))
    member_name = db.Column(db.String(100))
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(100))
    channel = db.Column(db.String(50))

with app.app_context():
    db.create_all()

# ==========================================  
# GOOGLE SHEETS & HELPERS  
# ==========================================  
SCOPE = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]  
gc_instance = None  

def get_gspread_client():  
    global gc_instance  
    if gc_instance is not None:  
        return gc_instance  
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")  
    if creds_json:  
        creds_dict = json.loads(creds_json)  
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPE)  
    elif os.path.exists("credentials.json"):  
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPE)  
    else:  
        raise RuntimeError("Google Credentials not found.")  
    gc_instance = gspread.authorize(creds)  
    return gc_instance  

def get_nairobi_timestamp():  
    return datetime.now(NAIROBI_TZ).strftime("%Y-%m-%d %H:%M:%S")  

def normalize_phone(phone):  
    if not phone:  
        return ""  
    digits = re.sub(r"\D", "", str(phone))  
    if digits.startswith("0") and len(digits) == 10:  
        return "254" + digits[1:]  
    elif digits.startswith("254") and len(digits) == 12:  
        return digits  
    elif len(digits) == 9:  
        return "254" + digits  
    return digits  

def is_duplicate_transaction(sheet, ref_id):  
    try:  
        if GymPaymentRecord.query.filter_by(ref_id=ref_id.strip().upper()).first():  
            return True  
        col_b = [str(x).strip().upper() for x in sheet.col_values(2)]  
        return ref_id.strip().upper() in col_b  
    except Exception as e:  
        logger.error(f"Duplicate check error: {e}")  
        return False  

# ==========================================  
# ROUTES  
# ==========================================  

@app.route('/mpesa-webhook', methods=['GET', 'POST'])
def mpesa_webhook():  
    return gym_portal()

@app.route('/mpesa-webhook', methods=['GET', 'POST'])
def mpesa_webhook():
    # Safaricom validation ping (GET or POST)
    if request.method == 'GET' or not request.is_json:
        return jsonify({
            "ResultCode": 0,
            "ResultDesc": "Accepted"
        })

    data = request.get_json(force=True, silent=True) or {}
    logging.info(f"Received M-Pesa Payload: {data}")

    # Check if this is a validation ping payload
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

    except Exception as e:
        logging.error(f"Error processing payment payload: {e}")

    return jsonify({
        "ResultCode": 0,
        "ResultDesc": "Success"
    })

@app.route("/receipt/<ref_id>", methods=["GET"])  
def generate_pdf_receipt(ref_id):  
    member_name = "Gym Member"  
    amount = 0.0  
    date = get_nairobi_timestamp()  

    try:
        client = get_gspread_client()
        sh = client.open_by_key(GYM_SHEET_ID)
        ws = sh.worksheet("Sheet1")
        for row in ws.get_all_records():
            norm = {str(k).strip().lower(): v for k, v in row.items()}
            p_ref = str(norm.get("ref") or norm.get("receipt") or row.get(list(row.keys())[1], "")).strip().upper()
            if p_ref == str(ref_id).strip().upper():
                member_name = str(norm.get("member") or norm.get("name") or "Gym Member")
                amount = float(str(norm.get("amount") or 0).replace(",", ""))
                date = str(norm.get("timestamp") or get_nairobi_timestamp())
                break
    except Exception as e:
        logger.error(f"Receipt fetch error: {e}")

    buffer = io.BytesIO()  
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)  
    styles = getSampleStyleSheet()  

    story = [  
        Paragraph(f"<b>{GYM_NAME}</b>", ParagraphStyle('T', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1E3A8A'), spaceAfter=1)),  
        Paragraph("<b>OFFICIAL MEMBERSHIP PAYMENT RECEIPT</b>", ParagraphStyle('S', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#0D9488'), spaceAfter=15)),  
        Paragraph(f"<b>Receipt Reference:</b> {ref_id}", ParagraphStyle('Meta1', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#334155'))),  
        Paragraph(f"<b>Date Issued:</b> {date}", ParagraphStyle('Meta2', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#334155'), spaceAfter=15)),  
    ]  

    table_data = [  
        ["Payment Field", "Details"],  
        ["Paybill Number", GYM_SHORTCODE],  
        ["Member Name", member_name],  
        ["Amount Paid", f"KES {amount:,.2f}"],  
        ["Payment Channel", "M-Pesa C2B"],  
        ["Account Status", "Fully Paid & Active"]  
    ]  

    t = Table(table_data, colWidths=[160, 320])  
    t.setStyle(TableStyle([  
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#1E3A8A')),  
        ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),  
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),  
        ('TOPPADDING', (0, 0), (-1, -1), 8),  
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),  
    ]))  
    story.append(t)  
    doc.build(story)  
    buffer.seek(0)  
    return send_file(buffer, as_attachment=False, download_name=f"Receipt_{ref_id}.pdf", mimetype="application/pdf")  

@app.route("/portal", methods=["GET"])  
def gym_portal():  
    try:
        client = get_gspread_client()
        sh = client.open_by_key(GYM_SHEET_ID)
        ws = sh.worksheet("Sheet1")
        records = ws.get_all_records()
    except Exception:
        records = []

    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>{{ gym_name }} Portal</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-950 text-slate-100 p-8 font-sans">
        <div class="max-w-4xl mx-auto space-y-6">
            <h1 class="text-2xl font-black text-white">{{ gym_name }} Payment Logs (Paybill: {{ paybill }})</h1>
            <div class="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
                <table class="w-full text-left border-collapse text-sm">
                    <thead class="bg-slate-800 text-slate-300 uppercase text-xs">
                        <tr>
                            <th class="p-4">Timestamp</th>
                            <th class="p-4">Reference</th>
                            <th class="p-4">Phone</th>
                            <th class="p-4">Member</th>
                            <th class="p-4">Amount</th>
                            <th class="p-4">Status</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-800">
                        {% for r in records | reverse %}
                        <tr class="hover:bg-slate-800/50">
                            <td class="p-4 font-mono text-xs text-slate-400">{{ r.get('Timestamp') or r.get('timestamp') }}</td>
                            <td class="p-4 font-mono font-bold text-blue-400">{{ r.get('Ref') or r.get('ref_id') }}</td>
                            <td class="p-4 font-mono">{{ r.get('Phone') or r.get('phone_number') }}</td>
                            <td class="p-4">{{ r.get('Member') or r.get('member_name') }}</td>
                            <td class="p-4 font-mono text-emerald-400 font-bold">KES {{ r.get('Amount') or r.get('amount') }}</td>
                            <td class="p-4"><span class="bg-emerald-500/10 text-emerald-400 px-2.5 py-1 rounded-md text-xs font-bold">Paid</span></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, gym_name=GYM_NAME, paybill=GYM_SHORTCODE, records=records)

if __name__ == "__main__":  
    app.run(debug=True, port=5001)