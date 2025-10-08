import psycopg
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from psycopg.rows import dict_row
import xml.etree.ElementTree as ET
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

load_dotenv()

db_url = os.getenv("DATABASE_URL")

# Fix Render's postgres:// issue for psycopg
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# ----- Database functions -----
def create_database():
    with psycopg.connect(db_url) as con:
        with con.cursor() as cur:
            cur.execute('''CREATE TABLE IF NOT EXISTS items(
                Id SERIAL PRIMARY KEY, 
                Name TEXT, 
                Type TEXT, 
                Quantity INTEGER, 
                ML INTEGER
            )''')
            con.commit()

def insert_record(name, type, quantity, ml):
    with psycopg.connect(db_url) as con:
        with con.cursor() as cur:
            cur.execute('''INSERT INTO items (Name, Type, Quantity, ML)
                           VALUES (%s, %s, %s, %s)''', (name, type, quantity, ml))
            con.commit()

def retrieve_records():
    with psycopg.connect(db_url, row_factory=dict_row) as con:
        with con.cursor() as cur:
            cur.execute("SELECT * FROM items")
            records = cur.fetchall()
            return records

def retrieve_by_name(name):
    with psycopg.connect(db_url, row_factory=dict_row) as con:
        with con.cursor() as cur:
            cur.execute("SELECT * FROM items WHERE Name = %s", (name,))
            records = cur.fetchall()
            return records

def delete_records(name):
    with psycopg.connect(db_url) as con:
        with con.cursor() as cur:
            cur.execute("DELETE FROM items WHERE Name = %s", (name,))
            con.commit()

def update_quantity(name, new_quantity):
    with psycopg.connect(db_url) as con:
        with con.cursor() as cur:
            cur.execute("UPDATE items SET Quantity = %s WHERE Name = %s",
                        (new_quantity, name))
            con.commit()

# ----- Flask App -----
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "fallbacksecret")

@app.route('/items/get', methods=['GET'])
def retrieve():
    items = retrieve_records()
    return jsonify(items)

@app.route('/items/post', methods=['POST'])
def add_item():
    data = request.get_json()
    name = data.get('name')
    type = data.get('type')
    quantity = data.get('quantity')
    ml = data.get('ml')

    if not all([name, type, quantity, ml]):
        return jsonify({"error": "Missing required field"}), 400

    insert_record(name, type, quantity, ml)
    return jsonify({
        'message': 'Item added successfully',
        'item': data
    }), 201

@app.route('/items/quantities', methods=['PATCH'])
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
@app.route('/items/delete', methods=['DELETE'])
def delete_item():
    data = request.get_json()
    name = data.get("name")

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
    items = request.get_json()

    # Create XML structure
    root = ET.Element("drinks")
    for item in items:
        drink = ET.SubElement(root, "item")
        ET.SubElement(drink, "name").text = str(item["Name"])
        ET.SubElement(drink, "type").text = str(item["Type"])
        ET.SubElement(drink, "quantity").text = str(item["Quantity"])
        ET.SubElement(drink, "ml").text = str(item["ML"])

    xml_data = ET.tostring(root, encoding="utf-8", xml_declaration=True).decode()
    file_path = "drinks.xml"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(xml_data)

    # Send email with attachment
    sender = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    receiver = os.getenv("EMAIL_RECEIVER")

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = receiver
    msg["Subject"] = "Drinks Inventory XML"
    msg.attach(MIMEText("Attached is the drinks XML file.", "plain"))

    with open(file_path, "rb") as f:
        part = MIMEApplication(f.read(), Name=os.path.basename(file_path))
        part["Content-Disposition"] = f'attachment; filename="{os.path.basename(file_path)}"'
        msg.attach(part)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
        return "XML file sent successfully!"
    except Exception as e:
        print(e)
        return "Error sending email", 500
    finally:
        os.remove(file_path)

if __name__ == "__main__":
    create_database()
    app.run(host="0.0.0.0", port=5000, debug=True)
