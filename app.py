import os
import re
from datetime import datetime, timedelta
import imaplib
import email
import pdfplumber
from flask import Flask, render_template, send_from_directory, request

app = Flask(__name__)

# E-Mail-Anmeldedaten und IMAP-Server
username = "alexschoon@gmx.de"
password = "DritteBremsleuchte"
imap_server = "imap.gmx.de"

# Basisverzeichnis für PDF-Dateien
pdf_base_dir = "static/Kues_Zweitschriften"
os.makedirs(pdf_base_dir, exist_ok=True)

@app.route('/')
def index():
    # Struktur für Kennzeichen aufbauen
    license_plate_structure = build_license_plate_structure()
    
    # Suchfeld
    search_query = request.args.get('search', '')
    
    # Filter für die Kennzeichen basierend auf der Suche
    if search_query:
        license_plate_structure = {k: v for k, v in license_plate_structure.items() if search_query.lower() in k.lower()}
    
    return render_template('index.html', license_plate_structure=license_plate_structure, search_query=search_query)

def connect_and_search_emails():
    download_count = 0
    duplicate_count = 0
    with imaplib.IMAP4_SSL(imap_server) as mail:
        mail.login(username, password)
        mail.select("inbox")

        # E-Mails der letzten 10 Tage abrufen
        date_since = (datetime.now() - timedelta(days=10)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'SINCE {date_since}', 'FROM', 'alexander.schoon@kues.de')
        if status != "OK":
            return download_count, duplicate_count

        email_ids = messages[0].split()

        # Verarbeitung jeder E-Mail und ihrer Anhänge
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
    # Verarbeitung der Anhänge einer E-Mail
    attachment_count = 0
    duplicate_count = 0
    for part in msg.walk():
        if part.get_content_disposition() == "attachment" and part.get_filename():
            filename = part.get_filename()
            # Prüfen, ob der Anhang eine gültige Datei ist
            if re.match(r"^\d{8}", filename):
                result, message = save_attachment(part, filename)
                if result == "downloaded":
                    attachment_count += 1
                elif result == "duplicate":
                    duplicate_count += 1
    return attachment_count, duplicate_count

def extract_license_plate_and_total(file_path):
    # Extraktion von Kennzeichen und Endsumme
    license_plate = None
    total_amount = None
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not license_plate:
                # Kennzeichen im Format "ABC-XY123" suchen
                match = re.search(r"\b([A-Z]{1,3}-[A-Z0-9]{1,2}[0-9]{1,4})\b", text)
                if match:
                    license_plate = match.group(0)
            if not total_amount:
                # Endsumme mit optionalen Leerzeichen und Groß/Kleinschreibung suchen
                match = re.search(r"(?i)Endsumme[:\s]*([\d.,]+)", text)
                if match:
                    total_amount = match.group(1)
            if license_plate and total_amount:
                break
    return license_plate, total_amount

def save_attachment(part, filename):
    # Temporäre Datei speichern
    temp_file_path = os.path.join("temp", filename)
    os.makedirs("temp", exist_ok=True)

    with open(temp_file_path, "wb") as f:
        f.write(part.get_payload(decode=True))

    # Extrahieren der Daten aus der PDF-Datei
    license_plate, total_amount = extract_license_plate_and_total(temp_file_path)
    final_file_path = os.path.join(pdf_base_dir, filename)

    # Prüfen, ob die Datei ein Duplikat ist
    if not os.path.exists(final_file_path):
        os.rename(temp_file_path, final_file_path)
        return "downloaded", f"Gespeichert: {final_file_path}"
    else:
        os.remove(temp_file_path)
        return "duplicate", f"Duplikat: {filename}"

def build_license_plate_structure():
    # Aufbau einer Struktur nach Kennzeichen
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

    # Umkehrung der Struktur, um die neuesten Einträge oben zu haben
    return {k: v for k, v in sorted(structure.items(), key=lambda item: item[1][0]['filename'], reverse=True)}

@app.route('/pdfs/<path:filename>')
def send_pdf(filename):
    return send_from_directory(pdf_base_dir, filename)

if __name__ == '__main__':
    app.run(debug=True)
