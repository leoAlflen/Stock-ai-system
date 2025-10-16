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
from psycopg import sql

load_dotenv()



db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL environment variable not set")

# Fix Render's postgres:// issue for psycopg
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)


# ----- NEW CORE DATABASE FUNCTIONS -----

def get_stock_data():
    """
    Fetches all drinks and joins them with their stock levels at each location.
    This is the main data-fetching function for your app.
    """
    query = """
        SELECT
    d.drinkid,
    d.name,
    d.type,
    d.volumeml,
    s.locationid,
    l.locationname,
    COALESCE(s.quantity, 0) AS quantity
    FROM
        drinks d
    JOIN stock s ON s.drinkid = d.drinkid
    JOIN locations l ON l.locationid = s.locationid
    -- optional filters
    WHERE s.quantity IS NOT NULL
    ORDER BY d.drinkid, l.locationname;
    """
    with psycopg.connect(db_url, row_factory=dict_row) as con:
        with con.cursor() as cur:
            cur.execute(query)
            flat_results = cur.fetchall()

    # Process the flat results into a nested structure the frontend expects
    drinks_dict = {}
    for row in flat_results:
        drink_id = row['drinkid']
        if drink_id not in drinks_dict:
            drinks_dict[drink_id] = {
                "DrinkID": drink_id,
                "Name": row['name'],
                "Type": row['type'],
                "VolumeML": row['volumeml'],
                "stock": []
            }

        drinks_dict[drink_id]["stock"].append({
            "LocationID": row['locationid'],
            "LocationName": row['locationname'],
            # Use COALESCE in SQL or handle None here to ensure quantity is a number
            "Quantity": row['quantity'] if row['quantity'] is not None else 0
        })
    
    return list(drinks_dict.values())

def get_locations_data():
    """Fetches all location records."""
    with psycopg.connect(db_url, row_factory=dict_row) as con:
        with con.cursor() as cur:
            cur.execute("SELECT * FROM Locations;")
            return cur.fetchall()



# ----- Flask App -----
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "fallbacksecret")


@app.route('/stock', methods=['GET'])
def get_current_stock():
    """Endpoint to get the full inventory picture."""
    items = get_stock_data()
    return jsonify(items)

@app.route('/locations', methods=['GET'])
def get_all_locations():
    """Endpoint to get the list of possible locations."""
    locations = get_locations_data()
    return jsonify(locations)

@app.route('/drinks', methods=['POST'])
def add_drink():
    """
    Adds a new master drink and creates stock entries ONLY at selected locations.
    """
    data = request.get_json()
    name = data.get('Name')
    drink_type = data.get('Type')
    ml = data.get('VolumeML')
    location_ids = data.get('LocationIDs', [])  # Get the array of selected location IDs

    # Validation
    if not all([name, drink_type, ml]):
        return jsonify({"error": "Missing required field (Name, Type, VolumeML)"}), 400
    
    if not location_ids or len(location_ids) == 0:
        return jsonify({"error": "At least one location must be selected"}), 400

    try:
        with psycopg.connect(db_url) as con:
            with con.cursor() as cur:
                # 1. Check if drink already exists
                cur.execute("SELECT DrinkID FROM Drinks WHERE Name = %s", (name,))
                if cur.fetchone():
                    return jsonify({"message": f"Drink '{name}' already exists"}), 409

                # 2. Insert the new drink and get its ID back
                cur.execute(
                    "INSERT INTO Drinks (Name, Type, VolumeML) VALUES (%s, %s, %s) RETURNING DrinkID",
                    (name, drink_type, ml)
                )
                new_drink_id = cur.fetchone()[0]

                # 3. Create initial stock records ONLY for selected locations
                for location_id in location_ids:
                    cur.execute(
                        "INSERT INTO Stock (DrinkID, LocationID, Quantity) VALUES (%s, %s, %s)",
                        (new_drink_id, location_id, 0)
                    )
                
                # 4. Commit all changes at once
                con.commit()

        return jsonify({
            "message": f"Drink '{name}' added successfully",
            "item": {
                "DrinkID": new_drink_id,
                "Name": name,
                "Type": drink_type,
                "VolumeML": ml
            }
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route('/transactions/stocktake', methods=['POST'])
def create_stocktake_transaction():
    """
    The main endpoint for recording a stocktake count. It creates a transaction
    and updates the current stock level.
    """
    data = request.get_json()
    drink_id = data.get("DrinkID")
    location_id = data.get("LocationID")
    new_quantity = int(data.get("NewQuantity", 0))

    try:
        with psycopg.connect(db_url) as con:
            with con.cursor() as cur:
                # 1. Get the current quantity from the Stock table
                cur.execute(
                    "SELECT Quantity FROM Stock WHERE DrinkID = %s AND LocationID = %s",
                    (drink_id, location_id)
                )
                result = cur.fetchone()
                old_quantity = result[0] if result else 0

                # 2. Calculate the change
                quantity_change = new_quantity - old_quantity
                if quantity_change == 0:
                    return jsonify({"message": "No change in quantity"}), 200

                # 3. Insert a record into the Transactions table (the history log)
                cur.execute(
                    "INSERT INTO Transactions (DrinkID, LocationID, QuantityChange, TransactionType) VALUES (%s, %s, %s, %s)",
                    (drink_id, location_id, quantity_change, 'STOCKTAKE_ADJUSTMENT')
                )

                # 4. Update the Stock table with the new, correct quantity
                cur.execute(
                    "UPDATE Stock SET Quantity = %s WHERE DrinkID = %s AND LocationID = %s",
                    (new_quantity, drink_id, location_id)
                )
                
                # 5. Commit both changes
                con.commit()
        
        return jsonify({"message": "Stocktake recorded and stock updated"}), 201


    except Exception as e:
        return jsonify({"error": str(e)}), 500


#Delete item
@app.route('/drinks', methods=['DELETE'])
def delete_item():
    data = request.get_json()
    name = data.get("Name")

    if not name:
        return jsonify({"Error": "Item name required"}), 400
     
    with psycopg.connect(db_url) as con:
        with con.cursor() as cur:
            cur.execute("DELETE FROM Drinks WHERE Name = %s", (name,))
            con.commit()
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
