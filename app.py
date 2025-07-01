import _sqlite3 as sqlite3

# This code creates a SQLite database, creates a table, inserts a record, and retrieves it.
# It uses the sqlite3 module to interact with the database.

dbstring = 'stockDatabase.db'

def create_database():
    con = sqlite3.connect(dbstring)
    cur = con.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS stock(Name TEXT, quantity INTEGER, price REAL)''')
    con.commit()
    con.close()

def insert_record(name, quantity, price):
    con = sqlite3.connect(dbstring)
    cur = con.cursor()
    cur.execute('''INSERT INTO stock(Name, quantity, price) VALUES(?, ?, ?)''', (name, quantity, price))
    con.commit()
    con.close()

def retrieve_records():
    con = sqlite3.connect(dbstring)
    cur = con.cursor()
    cur.execute('''SELECT * FROM stock''')
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
@app.route('/items/get/<string:item_Name>', methods=['GET'])
def retrieve(item_Name):
     con = sqlite3.connect(dbstring)
     con.row_factory = sqlite3.Row
     cur = con.cursor()
     cur.execute('select * from stock where Name = ?',(item_Name,))
     items = cur.fetchone()
     con.close()

     if items is None:
          return jsonify({'error ':' Item not found'}), 404
     
     return jsonify(dict(items)) 

#Input Information into the db
@app.route('/items/post/', methods=['POST'])
def add_item():
    print(" POST received")
    data = request.get_json()
    name = data.get('Name')
    quantity = data.get('Quantity')
    price = data.get('Price')

    if not name or quantity is None or price is None:
        return jsonify({"error": "Missing required field"}), 400

    con = sqlite3.connect(dbstring)
    cur = con.cursor()
    cur.execute("INSERT INTO stock (Name, Quantity, Price) VALUES (?, ?, ?)",
                (name, quantity, price))
    con.commit()
    con.close()

    return jsonify({
        'message': 'Item added successfully',
        'item': {
            'Name': name,
            'Quantity': quantity,
            'Price': price
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
