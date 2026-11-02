
import sqlite3

conn = sqlite3.connect("file:sales.db?mode=ro", uri=True)
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(products)")
columns = cursor.fetchall()

print("Products table ke columns:")

for column in columns:
    print(column[1])

conn.close()
