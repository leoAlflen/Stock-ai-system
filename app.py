import _sqlite3 as sqlite3

# This code creates a SQLite database, creates a table, inserts a record, and retrieves it.
# It uses the sqlite3 module to interact with the database.

dbstring = 'stockDatabase.db'

def create_database():
    con = sqlite3.connect(dbstring)
    cur = con.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS stock(Id INTEGER PRIMARY KEY AUTOINCREMENT, Name TEXT, Type STRING, Quantity INTEGER, ML INTEGER, Serves Decimal)''')
    con.commit()
    con.close()

def insert_record(name, type, quantity, ml):
    con = sqlite3.connect(dbstring)
    cur = con.cursor()
    serves = calculate_serves(type,quantity, ml)
    cur.execute('''INSERT INTO stock(Name, Type, Quantity, ML, Serves) VALUES(? ,? ,?, ?, ?)''', (name, type,quantity, ml, serves))
    con.commit()
    con.close()

def calculate_serves(type,quantity, ml):
     if type == 'Gin' or type == 'Whiskey' or type == 'Vodka':
          serves = (ml / 35) * quantity
     else: serves = (ml / 25) * quantity

     return serves    

def retrieve_records(item_type):
    con = sqlite3.connect(dbstring)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute('''SELECT * FROM stock WHERE Type = ?''', (item_type,))
    records = cur.fetchall()
    con.close()
    return records

def retrieve_by_name(name):
    con = sqlite3.connect(dbstring)
    cur = con.cursor()
    cur.execute("SELECT * FROM stock where Name = ?", (name,))
    records = cur.fetchall()
    con.close()
    return records 

def delete_records(name):

        con = sqlite3.connect(dbstring)
        cur = con.cursor()
        cur.execute("DELETE FROM stock WHERE Name = ? ", (name,))
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


if __name__ == "__main__":
    
    create_database()

    app.run(debug=True)
    





    # answer = ''
    # while answer != '5':
    #     print("Insert a number to proceed")
    #     print("1- Insert a record \n 2- Retrieve records \n 3- Delete record  \n 4-search item  \n 5- Exit")
        
        
    #     answer = input("Enter your choice: ")
    #     if answer == '1':
    #         name = input("Enter the name of the stock: ")
    #         quantity = int(input("Enter the quantity: "))
    #         price = float(input("Enter the price: "))
    #         insert_record(name, quantity, price)
    #         print("Record inserted successfully.")
    #     elif answer == '2':
    #         records = retrieve_records()
    #         for record in records:
    #             print(record)
    #     elif answer == '3':
    #         records = retrieve_records()
    #         for record in records:
    #             print(record)
    #         item = input("Enter the item name to be deleted: ") 
    #         delete_records(item)
    #         records = retrieve_records()
    #         for record in records:
    #             print(record)
            
    #     elif answer == '4':
    #         item = input("Search for a item: ")
    #         records = retrieve_by_name(item)
    #         for record in records:
    #             print(record)

    #     elif answer == '5':
    #         print("Closing application")
    #     else:
    #         print("Invalid choice. Please try again.")
