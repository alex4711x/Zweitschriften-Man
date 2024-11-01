import os
import re
from datetime import datetime, timedelta
import imaplib
import email
import pdfplumber
from flask import Flask, render_template, send_from_directory

app = Flask(__name__)

# E-Mail-Anmeldedaten und IMAP-Server
username = "alexschoon@gmx.de"
password = "DritteBremsleuchte"
imap_server = "imap.gmx.de"

# PDF-Struktur
pdf_base_dir = "static/Kues_Zweitschriften"
os.makedirs(pdf_base_dir, exist_ok=True)

@app.route('/')
def index():
    # Rufe hier die Funktion zum Abrufen der E-Mails auf
    download_count, duplicate_count = connect_and_search_emails()
    
    # Baue die PDF-Struktur nach dem Abrufen der PDFs
    pdf_structure = build_pdf_structure()
    license_plate_structure = build_license_plate_structure()
    
    return render_template('index.html', 
                           pdf_structure=pdf_structure, 
                           license_plate_structure=license_plate_structure,
                           download_count=download_count, 
                           duplicate_count=duplicate_count)

def connect_and_search_emails():
    download_count = 0
    duplicate_count = 0
    with imaplib.IMAP4_SSL(imap_server) as mail:
        mail.login(username, password)
        mail.select("inbox")

        date_since = (datetime.now() - timedelta(days=10)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'SINCE {date_since}', 'FROM', 'alexander.schoon@kues.de')
        if status != "OK":
            return download_count, duplicate_count

        email_ids = messages[0].split()

        for email_id in email_ids:
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            if status != "OK":
                continue

            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    attachments, duplicates = process_email(msg)
                    download_count += attachments
                    duplicate_count += duplicates

    return download_count, duplicate_count

def process_email(msg):
    attachment_count = 0
    duplicate_count = 0
    for part in msg.walk():
        if part.get_content_disposition() == "attachment" and part.get_filename():
            filename = part.get_filename()
            if re.match(r"^\d{8}", filename):
                result, message = save_attachment(part, filename)
                if result == "downloaded":
                    attachment_count += 1
                elif result == "duplicate":
                    duplicate_count += 1
    return attachment_count, duplicate_count

def extract_license_plate_and_total(file_path):
    license_plate = None
    total_amount = None
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not license_plate:
                match = re.search(r"\b([A-Z]{1,3}-[A-Z0-9]{1,2}[0-9]{1,4})\b", text)
                if match:
                    license_plate = match.group(0)
            if not total_amount:
                match = re.search(r"Endsumme:\s*([\d.,]+)", text)
                if match:
                    total_amount = match.group(1)
            if license_plate and total_amount:
                break
    return license_plate, total_amount

def save_attachment(part, filename):
    temp_file_path = os.path.join("temp", filename)
    os.makedirs("temp", exist_ok=True)

    with open(temp_file_path, "wb") as f:
        f.write(part.get_payload(decode=True))

    license_plate, total_amount = extract_license_plate_and_total(temp_file_path)
    final_file_path = os.path.join(pdf_base_dir, filename)

    if not os.path.exists(final_file_path):
        os.rename(temp_file_path, final_file_path)
        return "downloaded", f"Gespeichert: {final_file_path}"
    else:
        os.remove(temp_file_path)
        return "duplicate", f"Duplikat: {filename}"

def build_pdf_structure():
    structure = {}
    for root, dirs, files in os.walk(pdf_base_dir):
        for file in files:
            file_path = os.path.join(root, file)
            date_str = file[:8]
            try:
                file_date = datetime.strptime(date_str, "%Y%m%d")
            except ValueError:
                continue

            license_plate, total_amount = extract_license_plate_and_total(file_path)
            year = file_date.strftime("%Y")
            month = file_date.strftime("%B")
            day = file_date.strftime("%d") + " " + file_date.strftime("%A")

            file_info = {
                'filename': file,
                'license_plate': license_plate,
                'total_amount': total_amount
            }

            if year not in structure:
                structure[year] = {}
            if month not in structure[year]:
                structure[year][month] = {}
            if day not in structure[year][month]:
                structure[year][month][day] = []
            structure[year][month][day].append(file_info)
    return structure

def build_license_plate_structure():
    structure = {}
    for file in os.listdir(pdf_base_dir):
        if re.match(r"^\d{8}", file):
            file_path = os.path.join(pdf_base_dir, file)
            license_plate, total_amount = extract_license_plate_and_total(file_path)
            if license_plate:
                if license_plate not in structure:
                    structure[license_plate] = []
                structure[license_plate].append({
                    'filename': file,
                    'total_amount': total_amount
                })
    return structure

@app.route('/pdfs/<path:filename>')
def send_pdf(filename):
    return send_from_directory(pdf_base_dir, filename)

if __name__ == '__main__':
    app.run(debug=True)
