import re
import imaplib
import email
import pdfplumber
from flask import Flask, render_template, send_file, request
from io import BytesIO
from datetime import datetime, timedelta

app = Flask(__name__)

# E-Mail-Anmeldedaten und IMAP-Server
username = "alexschoon@gmx.de"
password = "DritteBremsleuchte"
imap_server = "imap.gmx.de"

@app.route('/')
def index():
    # PDFs direkt aus den E-Mails abrufen
    email_attachments = get_email_attachments()
    
    # Suchfeld
    search_query = request.args.get('search', '').strip()
    
    # Filter für Kennzeichen basierend auf der Suche
    if search_query:
        search_query_regex = search_query.replace("*", ".*")
        email_attachments = {k: v for k, v in email_attachments.items() if re.search(search_query_regex, k, re.IGNORECASE)}
    
    return render_template('index.html', email_attachments=email_attachments, search_query=search_query)

def get_email_attachments():
    """Direkter Zugriff auf die E-Mails und Extraktion der PDFs."""
    attachments_dict = {}
    with imaplib.IMAP4_SSL(imap_server) as mail:
        mail.login(username, password)
        mail.select("inbox")

        # E-Mails der letzten 10 Tage abrufen
        date_since = (datetime.now() - timedelta(days=10)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'SINCE {date_since}', 'FROM', 'alexander.schoon@kues.de')
        if status != "OK":
            return attachments_dict

        email_ids = messages[0].split()
        for email_id in email_ids:
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            if status != "OK":
                continue

            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    process_email(msg, attachments_dict)

    return attachments_dict

def process_email(msg, attachments_dict):
    """Anhänge aus E-Mails extrahieren und Informationen abrufen, ohne sie zu speichern."""
    for part in msg.walk():
        if part.get_content_disposition() == "attachment" and part.get_filename():
            filename = part.get_filename()
            if re.match(r"^\d{8}", filename):
                file_data = part.get_payload(decode=True)
                license_plate, total_amount = extract_license_plate_and_total(file_data)
                if license_plate:
                    if license_plate not in attachments_dict:
                        attachments_dict[license_plate] = []
                    attachments_dict[license_plate].append({
                        'filename': filename,
                        'file_data': file_data,
                        'total_amount': total_amount
                    })

def extract_license_plate_and_total(file_data):
    """Extraktion von Kennzeichen und Endsumme direkt aus der PDF-Datei."""
    license_plate = None
    total_amount = None
    with pdfplumber.open(BytesIO(file_data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not license_plate:
                match = re.search(r"\b([A-Z]{1,3}-[A-Z0-9]{1,2}[0-9]{1,4})\b", text)
                if match:
                    license_plate = match.group(0)
            if not total_amount:
                match = re.search(r"(?i)Endsumme[:\s]*([\d.,]+)", text)
                if match:
                    total_amount = match.group(1)
            if license_plate and total_amount:
                break
    return license_plate, total_amount

@app.route('/pdf_view/<license_plate>/<filename>')
def view_pdf(license_plate, filename):
    """PDF-Inhalt direkt aus dem Speicher streamen."""
    email_attachments = get_email_attachments()
    for item in email_attachments.get(license_plate, []):
        if item['filename'] == filename:
            pdf_data = BytesIO(item['file_data'])
            return send_file(pdf_data, mimetype='application/pdf', as_attachment=False, download_name=filename)

if __name__ == '__main__':
    app.run(debug=True)
