
import sqlite3

conn = sqlite3.connect("sales.db")
cursor = conn.cursor()

question = input(
    "Apna question likho: "
).lower()

if "product" in question or "products" in question:
    if "1000" in question:
        sql = "SELECT * FROM products WHERE price > 1000"
    elif "sab" in question or "all" in question:
        sql = "SELECT * FROM products"
    else:
        sql = "SELECT * FROM products"

    print("\nGenerated SQL:")
    print(sql)

    cursor.execute(sql)
    rows = cursor.fetchall()

    print("\nResult:")
    for row in rows:
        print(row)

else:
    print("Abhi main sirf products se related questions samajhta hoon.")

conn.close()
