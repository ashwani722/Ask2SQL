
import sqlite3

conn = sqlite3.connect("file:sales.db?mode=ro", uri=True)
cursor = conn.cursor()

# Database ki sabhi tables ke naam dekho
cursor.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    ORDER BY name
""")

tables = cursor.fetchall()

for table in tables:
    table_name = table[0]
    print(f"\nTable: {table_name}")

    # Har table ke columns dekho
    cursor.execute(f'PRAGMA table_info("{table_name}")')
    columns = cursor.fetchall()

    for column in columns:
        print(f"  Column: {column[1]} | Type: {column[2]}")

conn.close()
