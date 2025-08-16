import _sqlite3 as sqlite3

# This code creates a SQLite database, creates a table, inserts a record, and retrieves it.
# It uses the sqlite3 module to interact with the database.

dbstring = 'stockDatabase.db'

#create database with stock table
def create_database():
    con = sqlite3.connect(dbstring)
    cur = con.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS stock(Id INTEGER PRIMARY KEY AUTOINCREMENT, Name TEXT, Type STRING, Quantity INTEGER, ML INTEGER)''')
    con.commit()
    con.close()

#create cocktails table
def create_cocktailTable():
     con = sqlite3.connect(dbstring)
     cur = con.cursor()
     cur.execute('''CREATE TABLE IF NOT EXISTS recipes(recipesId INTEGER PRIMARY KEY AUTOINCREMENT, recName TEXT, Type STRING, Quantity INTEGER, ML INTEGER)''')
     con.commit()
     con.close()

#insert records/rows/new items
def insert_record(name, type, quantity, ml):
    con = sqlite3.connect(dbstring)
    cur = con.cursor()
    
    cur.execute('''INSERT INTO stock(Name, Type, Quantity, ML) VALUES(? ,? ,?, ?)''', (name, type,quantity, ml))
    con.commit()
    con.close()


#retrieve records by type
def retrieve_records():
    con = sqlite3.connect(dbstring)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute('''SELECT * FROM stock ''')
    records = cur.fetchall()
    con.close()
    return records

#retrieve records by name
def retrieve_by_name(name):
    con = sqlite3.connect(dbstring)
    cur = con.cursor()
    cur.execute("SELECT * FROM stock where Name = ?", (name,))
    records = cur.fetchall()
    con.close()
    return records 

#delete records/rows/items
def delete_records(name):

        con = sqlite3.connect(dbstring)
        cur = con.cursor()
        cur.execute("DELETE FROM stock WHERE Name = ? ", (name,))
        con.commit()
        con.close()

      
def update_quantity(name, new_quantity):
     
    # update
     
     con = sqlite3.connect(dbstring)
     cur = con.cursor()
     cur.execute("UPDATE stock SET Quantity = ? WHERE Name = ?", (new_quantity, name))
     con.commit()
     con.close()

from flask import Flask, request, jsonify
from flask_cors import CORS 

app = Flask(__name__)
CORS(app)

#Get information from the db
@app.route('/items/get', methods=['GET'])
def retrieve():
     items = retrieve_records()

    
     items_list = [dict(item) for item in items]
     return jsonify(items_list)

#Input Information into the db
@app.route('/items/post', methods=['POST'])
def add_item():
    print(" POST received")
    data = request.get_json()
    name = data.get('name')
    type = data.get('type')
    quantity = data.get('quantity')
    ml = data.get('ml')
    

    if name is None or type is None or quantity is None or ml is None:
        return jsonify({"error": "Missing required field"}), 400

    insert_record(name, type, quantity, ml)

    return jsonify({
        'message': 'Item added successfully',
        'item': {
            'name': name,
            'type': type,
            'quantity': quantity,
            'ml' : ml,
        }
    }), 201

# Update Quantities
@app.route('/items/patch/quantities', methods=['PATCH'])
def update_all_quantities():
    data = request.get_json()
    print("Received Data", data)

    if not isinstance(data, list):
         return jsonify({"Error": "A list of item updates is required"}), 400
    
    updated = []
    failed = []

    for item in data: 
         name = item.get("Name")
         quantity = item.get("Quantity")
         
         if not name or quantity is None:
              failed.append(item)
              continue
         try:
              update_quantity(name,quantity)
              updated.append
              print("It works")
         except Exception as e:
              failed.append({**item, "error": str(e)})
              print("IT doesnt work")

    return jsonify({
         "Updated Items": updated,
        "Failed Updates": failed
    }), 200

##Delete Record/Item/Row
@app.route('/items/delete', methods =['DELETE'])
def delete_item():
     
     name = request.get_json()

     #sets the message
     item = retrieve_by_name(name)
     message = {'Item Deleted':'{name}'}
     if not item:
          message = {"Error":"Inexistent Item"}

     if name is None:
          return jsonify({"Error": "Item name required"})
     
     delete_records(name)

     return jsonify(message)

if __name__ == "__main__":
    
    create_database()

    app.run(debug=True)
    



