import psycopg
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from psycopg.rows import dict_row
import openpyxl
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
import base64

load_dotenv()

# --- Database Connection Setup ---
db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL environment variable not set")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# ----- CORE DATABASE FUNCTIONS -----

def get_stock_data():
    """
    Fetches ALL active drinks and ONLY locations where stock entries exist.
    """
    query = """
        SELECT 
            d.drinkid, d.name, d.type, d.volumeml,
            l.locationid, l.locationname,
            s.quantity
        FROM "drinks" d
        INNER JOIN "stock" s ON d.drinkid = s.drinkid
        INNER JOIN "locations" l ON s.locationid = l.locationid
        WHERE d.is_active = true
        ORDER BY d.name, l.locationname;
    """
    with psycopg.connect(db_url, row_factory=dict_row) as con:
        with con.cursor() as cur:
            cur.execute(query)
            flat_results = cur.fetchall()

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
    Adds a new master drink and creates stock entries at selected locations.
    """
    data = request.get_json()
    print(f"\n=== RECEIVED DATA ===")
    print(f"Full data: {data}")
    
    name = data.get('Name')
    drink_type = data.get('Type')
    ml = data.get('VolumeML')
    selected_locations = data.get('LocationName', [])
    
    print(f"Selected locations: {selected_locations}")
    print(f"Type: {type(selected_locations)}")
    print(f"Length: {len(selected_locations)}")
    print(f"===================\n")

    if not all([name, drink_type, ml]):
        return jsonify({"error": "Missing required field (Name, Type, VolumeML)"}), 400

    try:
        with psycopg.connect(db_url) as con:
            with con.cursor() as cur:
                # Check if drink already exists
                cur.execute('SELECT "drinkid" FROM "drinks" WHERE "name" = %s', (name,))
                if cur.fetchone():
                    cur.execute('UPDATE "drinks" SET is_active = true WHERE "name" = %s', (name,))
                    con.commit()
                    return jsonify({"message": "Item reactivated"}), 200

                # Insert new drink
                cur.execute(
                    'INSERT INTO "drinks" ("name", "type", "volumeml") VALUES (%s, %s, %s) RETURNING "drinkid"',
                    (name, drink_type, ml)
                )
                new_drink_id = cur.fetchone()[0]
               
                # Get all locations from database
                cur.execute('SELECT "locationid", "locationname" FROM "locations"')
                all_locations = cur.fetchall()
                
                print(f"All locations from DB: {all_locations}")

                # Only create stock entries for selected locations
                if len(selected_locations) > 0:
                    for location in all_locations:
                        location_id = location[0]
                        location_name = location[1]
                        
                        print(f"Checking: {location_name} in {selected_locations}? {location_name in selected_locations}")
                        
                        # Check if this location was selected
                        if location_name in selected_locations:
                            print(f"  -> CREATING stock entry for {location_name}")
                            cur.execute(
                                'INSERT INTO "stock" ("drinkid", "locationid", "quantity") VALUES (%s, %s, %s)',
                                (new_drink_id, location_id, 0)
                            )
                        else:
                            print(f"  -> SKIPPING {location_name}")
                else:
                    print("WARNING: No locations selected, not creating any stock entries")
                
                con.commit()
        return jsonify({"message": f"Drink '{name}' added successfully"}), 201
    except Exception as e:
        print(f"Error in add_drink: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/transactions/stocktake', methods=['POST'])
def create_stocktake_transaction():
    """
    Records stocktake transactions and updates stock quantities.
    """
    print("\n--- Received a request to /transactions/stocktake ---")
    data = request.get_json()
    print(f"1. Incoming JSON data from frontend: {data}")

    try:
        drink_id = data.get("DrinkID")
        location_id = data.get("LocationID")
        new_quantity = float(data.get("NewQuantity", 0))
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
                    old_quantity = float(result[0])
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
        return jsonify({"error": str(e)}), 500 
    
@app.route('/drinks/<int:drink_id>', methods=['DELETE'])
def deactivate_drink(drink_id):
    """
    Soft-deletes a drink by marking it as inactive.
    """
    try:
        with psycopg.connect(db_url) as con:
            with con.cursor() as cur:
                cur.execute(
                    'UPDATE "drinks" SET is_active = false WHERE "drinkid" = %s',
                    (drink_id,)
                )
                con.commit()
                if cur.rowcount == 0:
                    return jsonify({"Error": "Item not found"}), 404
        return jsonify({"message": "Item deactivated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/edit/<int:drink_id>', methods=['PUT'])
def update_drink(drink_id):
    """Updates an existing drink's details."""
    data = request.get_json()
    name = data.get('Name')
    drink_type = data.get('Type')
    ml = data.get('VolumeML')
    
    if not all([name, drink_type, ml]):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        with psycopg.connect(db_url) as con:
            with con.cursor() as cur:
                cur.execute(
                    "UPDATE drinks SET name = %s, type = %s, volumeml = %s WHERE drinkid = %s",
                    (name, drink_type, ml, drink_id)
                )
                con.commit()
        
        return jsonify({"message": "Drink updated successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/send-report", methods=["POST"])
def send_report():
    """Sends stock inventory report via SendGrid email."""
    data = request.get_json()
    custom_receiver = data.get('recipient')
    file_path = None
    
    try:
        # 1. Get stock data and create Excel file
        items_data = get_stock_data()

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Current Stock Report"
        ws.append(["Drink Name", "Type", "Volume (ML)", "Total Quantity"])
        
        for item in items_data:
            total_quantity = sum(stock_info["Quantity"] for stock_info in item['stock'])
            ws.append([
                item["Name"], 
                item["Type"], 
                item["VolumeML"], 
                total_quantity
            ])

        file_path = "stock_report.xlsx"
        wb.save(file_path)
        print(f"✓ Excel file created: {file_path}")

        # 2. Read and encode the file
        with open(file_path, 'rb') as f:
            file_data = f.read()
        encoded_file = base64.b64encode(file_data).decode()

        # 3. Get email configuration
        sender_email = os.getenv("EMAIL_USER")
        sendgrid_api_key = os.getenv("SENDGRID_API_KEY")
        
        if not all([sender_email, sendgrid_api_key, custom_receiver]):
            missing = []
            if not sender_email: missing.append("EMAIL_USER")
            if not sendgrid_api_key: missing.append("SENDGRID_API_KEY")
            if not custom_receiver: missing.append("recipient")
            return jsonify({"error": f"Missing configuration: {', '.join(missing)}"}), 500

        print(f"✓ Configuration loaded - Sender: {sender_email}, Receiver: {custom_receiver}")

        # 4. Create email message with SendGrid
        message = Mail(
            from_email=sender_email,
            to_emails=custom_receiver,
            subject='Stock Inventory Report',
            html_content=f'''
                <html>
                <body>
                    <p>Hello,</p>
                    <p>Please find attached the current stock inventory report.</p>
                    <p><strong>Total items in report:</strong> {len(items_data)}</p>
                    <p>Best regards,<br>Stock Management System</p>
                </body>
                </html>
            '''
        )

        # 5. Attach the Excel file
        attached_file = Attachment(
            FileContent(encoded_file),
            FileName('stock_report.xlsx'),
            FileType('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            Disposition('attachment')
        )
        message.attachment = attached_file

        print("✓ Email message created with attachment")

        # 6. Send email via SendGrid
        print("Sending email via SendGrid...")
        sg = SendGridAPIClient(sendgrid_api_key)
        response = sg.send(message)
        
        print(f"✓ Email sent successfully! Status code: {response.status_code}")
        return jsonify({"message": "Report sent successfully!"}), 200

    except Exception as e:
        error_msg = f"Error sending email: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": error_msg}), 500
        
    finally:
        # Clean up the temporary file
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            print(f"✓ Temporary file removed: {file_path}")

#Add new users
@app.route("/users", methods=["POST"])
def add_user():
    """Endpoint to add a new user."""
    data = request.get_json()
    fullname = data.get("name")
    email = data.get("email")
    role = data.get("role")

    if not all([fullname, email, role]):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        with psycopg.connect(db_url) as con:
            with con.cursor(row_factory=psycopg.rows.dict_row) as cur:
                # Check if user exists
                cur.execute('SELECT * FROM "users" WHERE email = %s', (email,))
                existing_user = cur.fetchone()

                if existing_user:
                    if not existing_user["is_active"]:
                        # Reactivate soft-deleted user
                        cur.execute(
                            'UPDATE "users" SET is_active = true WHERE email = %s RETURNING userid, name, email, role',
                            (email,)
                        )
                        reactivated_user = cur.fetchone()
                        con.commit()
                        return jsonify(reactivated_user), 200
                    else:
                        return jsonify({"error": "User already exists"}), 400

                # Insert new user
                cur.execute(
                    'INSERT INTO "users" (name, email, role) VALUES (%s, %s, %s) RETURNING userid, name, email, role',
                    (fullname, email, role)
                )
                new_user = cur.fetchone()
                con.commit()
                return jsonify(new_user), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

#Get all users
@app.route("/users", methods=["GET"])
def get_users():
    """Endpoint to get all users."""
    try:
        with psycopg.connect(db_url, row_factory=dict_row) as con:
            with con.cursor() as cur:
                cur.execute('SELECT * FROM "users";')
                users = cur.fetchall()
        return jsonify(users), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
#soft delete user
@app.route("/user/<int:user_id>", methods=["DELETE"])
def deactivate_user(user_id):
    """Soft-deletes a user by marking them as inactive."""
    try:
        with psycopg.connect(db_url) as con:
            with con.cursor() as cur:
                cur.execute(
                    'UPDATE "users" SET is_active = false WHERE "userid" = %s',
                    (user_id,)
                )
                con.commit()
                if cur.rowcount == 0:
                    return jsonify({"Error": "User not found"}), 404
        return jsonify({"message": "User deactivated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
 #Edit Users 
@app.route("/user/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    """Updates an existing user's details."""
    data = request.get_json()
    fullname = data.get('fullname')
    email = data.get('email')
    role = data.get('role')

    if not all([fullname, email, role]):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        with psycopg.connect(db_url) as con:
            with con.cursor() as cur:
                cur.execute(
                    "UPDATE users SET fullname = %s, email = %s, role = %s WHERE userid = %s",
                    (fullname, email, role, user_id)
                )
                con.commit()

        return jsonify({"message": "User updated successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)