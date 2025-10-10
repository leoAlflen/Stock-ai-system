import psycopg
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from psycopg.rows import dict_row
import xml.etree.ElementTree as ET
import smtplib
import openpyxl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

load_dotenv()

db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL environment variable not set")

# Fix Render's postgres:// issue for psycopg
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

def insert_record(name, type, quantity, ml):
    try:
        quantity = int(quantity)
        ml = int(ml)
    except (TypeError, ValueError):
        raise ValueError("Quantity and ML must be integers")
    with psycopg.connect(db_url) as con:
        with con.cursor() as cur:
            cur.execute('''INSERT INTO Drinks (Name, Type, Quantity, VolumeML)
                           VALUES (%s, %s, %s, %s)''', (name, type, quantity, ml))
            con.commit()

def retrieve_records():
    with psycopg.connect(db_url, row_factory=dict_row) as con:
        with con.cursor() as cur:
            cur.execute("SELECT * FROM Drinks")
            records = cur.fetchall()
            return records

def retrieve_by_name(name):
    with psycopg.connect(db_url, row_factory=dict_row) as con:
        with con.cursor() as cur:
            cur.execute("SELECT * FROM Drinks WHERE Name = %s", (name,))
            records = cur.fetchall()
            return records

def delete_records(name):
    with psycopg.connect(db_url) as con:
        with con.cursor() as cur:
            cur.execute("DELETE FROM Drinks WHERE Name = %s", (name,))
            con.commit()

def update_quantity(name, new_quantity):
    with psycopg.connect(db_url) as con:
        with con.cursor() as cur:
            cur.execute("UPDATE Drinks SET Quantity = %s WHERE Name = %s",
                        (new_quantity, name))
            con.commit()

# ----- Flask App -----
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "fallbacksecret")

@app.route('/drinks', methods=['GET'])
def retrieve():
    items = retrieve_records()
    return jsonify(items)

@app.route('/drinks', methods=['POST'])
def add_item():
    data = request.get_json()
    name = data.get('Name')
    type = data.get('Type')
    quantity = data.get('Quantiy')
    ml = data.get('VolumeML')

    if not all([name, type, quantity, ml]):
        return jsonify({"error": "Missing required field"}), 400

    insert_record(name, type, quantity, ml)
    return jsonify({
        'message': 'Item added successfully',
        'item': data
    }, 201)

@app.route('/drinks', methods=['PATCH'])
def update_all_quantities():
    data = request.get_json()

    if not isinstance(data, list):
        return jsonify({"Error": "A list of item updates is required"}), 400
    
    updated, failed = [], []

    for item in data: 
        name = item.get("name")
        quantity = item.get("quantity")
         
        if not name or quantity is None:
            failed.append(item)
            continue
        try:
            update_quantity(name, quantity)
            updated.append(item)
        except Exception as e:
            failed.append({**item, "error": str(e)})

    return jsonify({
        "Updated Items": updated,
        "Failed Updates": failed
    }), 200

#Delete item
@app.route('/drinks', methods=['DELETE'])
def delete_item():
    data = request.get_json()
    name = data.get("Name")

    if not name:
        return jsonify({"Error": "Item name required"}), 400
     
    item = retrieve_by_name(name)
    if not item:
        return jsonify({"Error": "Item does not exist"}), 404
     
    delete_records(name)
    return jsonify({"Item Deleted": name})

#Send email XML file 
@app.route("/send-xml", methods=["POST"])
def send_xml():
    # Fetch all items from DB
    items = retrieve_records()

    # Create XLSX workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Drinks"
    ws.append(["Name", "Type", "Quantity", "VolumeML"])
    for item in items:
        ws.append([item["Name"], item["Type"], item["Quantity"], item["VolumeML"]])

    file_path = "drinks.xlsx"
    wb.save(file_path)

    # Email credentials
    sender = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    receiver = os.getenv("EMAIL_RECEIVER")
    if not all([sender, password, receiver]):
        return "Email credentials not set", 500

    # Create email
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = receiver
    msg["Subject"] = "Drinks Inventory XLSX (All Items)"
    msg.attach(MIMEText("Attached is the drinks XLSX file with all items.", "plain"))

    with open(file_path, "rb") as f:
        part = MIMEApplication(f.read(), Name=os.path.basename(file_path))
        part["Content-Disposition"] = f'attachment; filename="{os.path.basename(file_path)}"'
        msg.attach(part)

    try:
        # Use SSL for Gmail
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.set_debuglevel(1)  # Print SMTP debug info
            print("Logging in...")
            server.login(sender, password)
            print("Login successful, sending email...")
            server.send_message(msg)
            print("Email sent successfully!")
        return "XLSX file sent successfully!"
    except smtplib.SMTPAuthenticationError as auth_err:
        print("SMTP Authentication Error:", auth_err)
        return f"SMTP Authentication Error: {auth_err}", 500
    except smtplib.SMTPException as smtp_err:
        print("SMTP Error:", smtp_err)
        return f"SMTP Error: {smtp_err}", 500
    except Exception as e:
        print("General Error:", e)
        return f"Error sending email: {e}", 500
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
            print("Temporary file removed.")
if __name__ == "__main__":

    app.run(host="0.0.0.0", port=5000, debug=True)
