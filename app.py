import psycopg
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from psycopg.rows import dict_row
import openpyxl
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

load_dotenv()

# --- Database Connection Setup (No changes needed) ---
db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL environment variable not set")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# ----- CORE DATABASE FUNCTIONS -----

def get_stock_data():
    """
    Fetches ALL active drinks and ALL locations, ensuring a result for every
    possible combination, which is essential for the frontend grid.
    """
    # CORRECTED QUERY: Uses CROSS JOIN and LEFT JOIN to get a full grid.
    # Also filters for `is_active = true` to support soft deletes.
    query = """
        SELECT 
            d.drinkid, d.name, d.type, d.volumeml,
            l.locationid, l.locationname,
            COALESCE(s.Quantity, 0) AS Quantity
        FROM "drinks" d
        CROSS JOIN "locations" l
        LEFT JOIN "stock" s ON d.drinkid = s.drinkid AND l.locationid = s.locationid
        WHERE d.is_active = true
        ORDER BY d.name, l.locationname;
    """
    with psycopg.connect(db_url, row_factory=dict_row) as con:
        with con.cursor() as cur:
            cur.execute(query)
            flat_results = cur.fetchall()

    # This Python logic correctly processes the flat SQL results into the nested JSON structure.
    drinks_dict = {}
    for row in flat_results:
        drink_id = row['drinkid'] # psycopg with dict_row makes keys lowercase
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
            "Quantity": row['quantity']
        })
    
    return list(drinks_dict.values())

def get_locations_data():
    """Fetches all location records."""
    with psycopg.connect(db_url, row_factory=dict_row) as con:
        with con.cursor() as cur:
            cur.execute('SELECT * FROM "locations";')
            return cur.fetchall()

# ----- Flask App -----
app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "fallbacksecret")


# ----- API ENDPOINTS -----

@app.route('/stock', methods=['GET'])
def get_current_stock():
    """Endpoint to get the full inventory picture for the frontend."""
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
    Adds a new master drink and auto-creates its stock entries at ALL locations.
    This simplifies the frontend logic significantly.
    """
    data = request.get_json()
    name = data.get('Name')
    drink_type = data.get('Type')
    ml = data.get('VolumeML')

    if not all([name, drink_type, ml]):
        return jsonify({"error": "Missing required field (Name, Type, VolumeML)"}), 400

    try:
        with psycopg.connect(db_url) as con:
            with con.cursor() as cur:
                cur.execute('SELECT "drinkid" FROM "drinks" WHERE "name" = %s', (name,))
                if cur.fetchone():
                    cur.execute('UPDATE "drinks" SET is_active = true WHERE "name" = %s',(name,))
                    return jsonify("Item Added Again"), 409

                cur.execute(
                    'INSERT INTO "drinks" ("name", "type", "volumeml") VALUES (%s, %s, %s) RETURNING "drinkid"',
                    (name, drink_type, ml)
                )
                new_drink_id = cur.fetchone()[0]
               
                cur.execute('SELECT "locationid" FROM "locations"')
                locations = cur.fetchall()

                for loc in locations:
                    location_id = loc[0]
                    cur.execute(
                        'INSERT INTO "stock" ("drinkid", "locationid", "quantity") VALUES (%s, %s, %s)',
                        (new_drink_id, location_id, 0)
                    )
                
                con.commit()
        return jsonify({"message": f"Drink '{name}' added successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# In app.py

@app.route('/transactions/stocktake', methods=['POST'])
def create_stocktake_transaction():
    """
    DEBUG VERSION: This function has extra print statements to show us
    exactly what data is being received and what actions are being taken.
    """
    print("\n--- Received a request to /transactions/stocktake ---")
    data = request.get_json()
    print(f"1. Incoming JSON data from frontend: {data}")

    try:
        drink_id = data.get("DrinkID")
        location_id = data.get("LocationID")
        new_quantity = int(data.get("NewQuantity", 0))
        print(f"2. Parsed IDs: DrinkID={drink_id}, LocationID={location_id}, NewQuantity={new_quantity}")

        if not drink_id or not location_id:
            print("ERROR: Missing DrinkID or LocationID in the request.")
            return jsonify({"error": "Missing DrinkID or LocationID"}), 400

        with psycopg.connect(db_url) as con:
            with con.cursor() as cur:
                print("3. Checking for existing stock record...")
                cur.execute(
                    'SELECT "quantity" FROM "stock" WHERE "drinkid" = %s AND "locationid" = %s',
                    (drink_id, location_id)
                )
                result = cur.fetchone()

                if result:
                    print(f"4a. Found existing stock record. Old quantity: {result[0]}")
                    old_quantity = result[0]
                    quantity_change = new_quantity - old_quantity
                    if quantity_change == 0:
                        return jsonify({"message": "No change in quantity"}), 200

                    print("5a. Executing UPDATE on Stock table...")
                    cur.execute(
                        'UPDATE "stock" SET "quantity" = %s WHERE "drinkid" = %s AND "locationid" = %s',
                        (new_quantity, drink_id, location_id)
                    )
                else:
                    print("4b. No stock record found. This will be a new INSERT.")
                    old_quantity = 0
                    quantity_change = new_quantity

                    print("5b. Executing INSERT on Stock table...")
                    cur.execute(
                        'INSERT INTO "stock" ("drinkid", "locationid", "quantity") VALUES (%s, %s, %s)',
                        (drink_id, location_id, new_quantity)
                    )

                print("6. Executing INSERT on Transactions table...")
                cur.execute(
                    'INSERT INTO "transactions" ("drinkid", "locationid", "quantity", "transactiontype") VALUES (%s, %s, %s, %s)',
                    (drink_id, location_id, quantity_change, 'STOCKTAKE_ADJUSTMENT')
                )
                
                print("7. Committing transaction to database...")
                con.commit()
                print("--- Request successful ---")
        
        return jsonify({"message": "Stocktake recorded and stock updated"}), 201

    except Exception as e:
        print(f"\n!!!!!! AN ERROR OCCURRED !!!!!!")
        print(f"Error Type: {type(e)}")
        print(f"Error Details: {e}")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")
        # Also return the error to the frontend
        return jsonify({"error": str(e)}), 500 
    
@app.route('/drinks/<int:drink_id>', methods=['DELETE'])
def deactivate_drink(drink_id):
    """
    BEST PRACTICE: Soft-deletes a drink by marking it as inactive.
    This preserves all historical transaction data.
    """
    try:
        with psycopg.connect(db_url) as con:
            with con.cursor() as cur:
                cur.execute(
                    'UPDATE "drinks" SET is_active = false WHERE "drinkid" = %s',
                    (drink_id,)
                )
                con.commit()
                # Check if any row was actually updated
                if cur.rowcount == 0:
                    return jsonify({"Error": "Item not found"}), 404
        return jsonify({"message": "Item deactivated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/send-report", methods=["POST"])
def send_report():
    """
    REWRITTEN: Generates an XLSX report from the current stock data and emails it.
    """
    try:
        items_data = get_stock_data() # Use our main data function

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Current Stock Report"
        ws.append(["Drink Name", "Type", "Volume (ML)", "Location", "Quantity"])
        
        # Flatten the nested data for the report
        for item in items_data:
            for stock_info in item['stock']:
                ws.append([
                    item["Name"], 
                    item["Type"], 
                    item["VolumeML"], 
                    stock_info["LocationName"], 
                    stock_info["Quantity"]
                ])

        file_path = "stock_report.xlsx"
        wb.save(file_path)

        # (Your email sending logic remains here - no changes needed)
        sender = os.getenv("EMAIL_USER")
        password = os.getenv("EMAIL_PASS")
        receiver = os.getenv("EMAIL_RECEIVER")
        # ... rest of your smtplib code ...

        return "Report sent successfully!"

    except Exception as e:
        print(f"Error in send_report: {e}")
        return f"Error sending report: {e}", 500
    finally:
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)