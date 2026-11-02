
import sqlite3

conn = sqlite3.connect("sales.db")
cursor = conn.cursor()

price_limit = int(input("Minimum price enter karo: "))

cursor.execute(
    "SELECT * FROM products WHERE price > ?",
    (price_limit,)
)

rows = cursor.fetchall()

if rows:
    print("\nProducts found:")
    for row in rows:
        print(f"ID: {row[0]} | Name: {row[1]} | Price: ₹{row[2]:,.0f}")
else:
    print("Koi product nahi mila.")

conn.close()
