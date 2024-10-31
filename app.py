from flask import Flask, render_template, send_from_directory, request
import os
import imaplib
import email
import re
from datetime import datetime, timedelta
import pdfplumber
import subprocess

app = Flask(__name__)

# E-Mail-Anmeldedaten und IMAP-Server
username = "Zweitschriften-man@gmx.de"
password = "Feststellbremsventil"  # Ersetze mit deinem Passwort
imap_server = "imap.gmx.de"

# Definiere den Hauptordner für die Zweitschriften
main_folder = "Kues Zweitschriften"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    last_10_days = request.form.get('last_10_days') == 'on'
    try:
        download_count, duplicate_count = connect_and_search_emails(last_10_days)
        message = f"Vorgang abgeschlossen! Neue Zweitschriften: {download_count}, Duplikate: {duplicate_count}"
    except Exception as e:
        message = f"Fehler: {e}"

    return render_template('index.html', message=message)

def connect_and_search_emails(last_10_days):
    download_count = 0
    duplicate_count = 0
    with imaplib.IMAP4_SSL(imap_server) as mail:
        mail.login(username, password)
        mail.select("inbox")

        # Bestimme das Datum, wenn "Nur die letzten 10 Tage herunterladen" ausgewählt ist
        if last_10_days:
            date_since = (datetime.now() - timedelta(days=10)).strftime("%d-%b-%Y")
            status, messages = mail.search(None, f'SINCE {date_since}', 'FROM', 'alexander.schoon@kues.de')
        else:
            status, messages = mail.search(None, 'FROM', 'alexander.schoon@kues.de')

        if status != "OK":
            raise Exception("Fehler bei der E-Mail-Suche.")
        
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

def save_attachment(part, filename):
    date_str = filename[:8]
    file_date = datetime.strptime(date_str, "%Y%m%d")
    temp_file_path = os.path.join("temp", filename)
    os.makedirs("temp", exist_ok=True)

    with open(temp_file_path, "wb") as f:
        f.write(part.get_payload(decode=True))

    final_file_path = os.path.join(main_folder, filename)
    if not os.path.exists(final_file_path):
        os.rename(temp_file_path, final_file_path)
        return "downloaded", f"Gespeichert: {final_file_path}"
    else:
        os.remove(temp_file_path)
        return "duplicate", f"Duplikat gefunden: {filename}"

@app.route('/files')
def files():
    files = []
    for dirpath, dirnames, filenames in os.walk(main_folder):
        for dirname in dirnames:
            files.append(os.path.join(dirpath, dirname))
        for filename in filenames:
            files.append(os.path.join(dirpath, filename))
    
    return render_template('files.html', files=files)

@app.route('/download/<path:filename>')
def download_file(filename):
    directory = os.path.dirname(filename)
    filename = os.path.basename(filename)
    return send_from_directory(directory, filename)

if __name__ == '__main__':
    app.run(debug=True)
