import _sqlite3 as sqlite3
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os

# ----- Load Environment Variables -----
load_dotenv()
dbstring = os.path.join(os.getcwd(), "default.db")
  # fallback if missing

# ----- Database functions -----
def create_database():
    con = sqlite3.connect(dbstring)
    cur = con.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS stock(
        Id INTEGER PRIMARY KEY AUTOINCREMENT, 
        Name TEXT, 
        Type TEXT, 
        Quantity INTEGER, 
        ML INTEGER
    )''')
    con.commit()
    con.close()

def insert_record(name, type, quantity, ml):
    con = sqlite3.connect(dbstring)
    cur = con.cursor()
    cur.execute('''INSERT INTO stock(Name, Type, Quantity, ML) VALUES(?, ?, ?, ?)''',
                (name, type, quantity, ml))
    con.commit()
    con.close()

def retrieve_records():
    con = sqlite3.connect(dbstring)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT * FROM stock")
    records = cur.fetchall()
    con.close()
    return records

def retrieve_by_name(name):
    con = sqlite3.connect(dbstring)
    cur = con.cursor()
    cur.execute("SELECT * FROM stock WHERE Name = ?", (name,))
    records = cur.fetchall()
    con.close()
    return records

def delete_records(name):
    con = sqlite3.connect(dbstring)
    cur = con.cursor()
    cur.execute("DELETE FROM stock WHERE Name = ?", (name,))
    con.commit()
    con.close()

def update_quantity(name, new_quantity):
    con = sqlite3.connect(dbstring)
    cur = con.cursor()
    cur.execute("UPDATE stock SET Quantity = ? WHERE Name = ?", (new_quantity, name))
    con.commit()
    con.close()

# ----- Flask App -----
app = Flask(__name__)
CORS(app)

# Load secret key from .env
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "fallbacksecret")

@app.route('/items/get', methods=['GET'])
def retrieve():
    items = retrieve_records()
    items_list = [dict(item) for item in items]
    return jsonify(items_list)

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

if __name__ == "__main__":
    create_database()
    app.run(host="0.0.0.0", port=5000, debug=True)

