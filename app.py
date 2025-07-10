import _sqlite3 as sqlite3

# This code creates a SQLite database, creates a table, inserts a record, and retrieves it.
# It uses the sqlite3 module to interact with the database.

dbstring = 'stockDatabase.db'

#create database
def create_database():
    con = sqlite3.connect(dbstring)
    cur = con.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS stock(Id INTEGER PRIMARY KEY AUTOINCREMENT, Name TEXT, Type STRING, Quantity INTEGER, ML INTEGER, Serves Decimal)''')
    con.commit()
    con.close()

#insert records/rows/new items
def insert_record(name, type, quantity, ml):
    con = sqlite3.connect(dbstring)
    cur = con.cursor()
    serves = calculate_serves(type, ml)
    cur.execute('''INSERT INTO stock(Name, Type, Quantity, ML, Serves) VALUES(? ,? ,?, ?, ?)''', (name, type,quantity, ml, serves))
    con.commit()
    con.close()

#calculates the serves for each beverage
def calculate_serves(type, ml):
     if type == 'Gin' or type == 'Whiskey' or type == 'Vodka':
          serves = (ml / 35)
     elif type == 'Keg':
            serves = (ml / 500)
     elif type == 'Syrup':
        serves = (ml/25)
     elif type == 'Bottle':
          serves = ml / ml

     return serves    

#retrieve records by type
def retrieve_records(item_type):
    con = sqlite3.connect(dbstring)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute('''SELECT * FROM stock WHERE Type = ?''', (item_type,))
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

app = Flask(__name__)

#Get information from the db
@app.route('/items/get/<string:item_type>', methods=['GET'])
def retrieve(item_type):
     items = retrieve_records(item_type)

     if not items:
          return jsonify({'error ':' Item not found'}), 404
     
     items_list = [dict(item) for item in items]
     return jsonify(items_list)

#Input Information into the db
@app.route('/items/post/', methods=['POST'])
def add_item():
    print(" POST received")
    data = request.get_json()
    name = data.get('Name')
    type = data.get('Type')
    quantity = data.get('Quantity')
    ml = data.get('ML')
    

    if name is None or type is None or quantity is None or ml is None:
        return jsonify({"error": "Missing required field"}), 400

    insert_record(name, type, quantity, ml)

    return jsonify({
        'message': 'Item added successfully',
        'item': {
            'Name': name,
            'Type': type,
            'Quantity': quantity,
            'ML' : ml,
        }
    }), 201

# Update Quantity
@app.route('/items/patch/quantity/<string:name>', methods=['PATCH'])
def update_item(name):
     data = request.get_json()
     new_quantity = data.get("Quantity")

     if new_quantity is None:
          return jsonify({"Error" : "Quantity required"}), 400
    
     update_quantity(name, new_quantity)

     return jsonify({'Quantity Updated" : "Quantity for {name} updated to {new_quantity}'}), 200

##Delete Record/Item/Row
@app.route('/items/delete/<string:name>', methods =['DELETE'])
def delete_item(name):
     
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
    



