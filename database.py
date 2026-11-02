
import sqlite3

# Database se connection banao
connection = sqlite3.connect("sales.db")

# SQL commands chalane ke liye cursor
cursor = connection.cursor()

# Products table banao
cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    price REAL NOT NULL
)
""")

# Orders table banao
cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY,
    product_id INTEGER,
    quantity INTEGER NOT NULL,
    order_date TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
)
""")

# Sample products insert karo
cursor.executemany("""
INSERT OR IGNORE INTO products
(product_id, product_name, price)
VALUES (?, ?, ?)
""", [
    (1, "Laptop", 50000),
    (2, "Mobile", 20000),
    (3, "Headphones", 1000),
])

# Sample orders insert karo
cursor.executemany("""
INSERT INTO orders
(order_id, product_id, quantity, order_date)
VALUES (?, ?, ?, ?)
ON CONFLICT(order_id) DO NOTHING
""", [
    (101, 1, 2, "2026-10-05"),
    (102, 2, 5, "2026-10-10"),
    (103, 3, 10, "2026-10-15"),
    (104, 1, 1, "2026-10-20"),
    (105, 3, 20, "2026-10-25"),
])

# Changes save karo
connection.commit()

# Products ka data dikhao
cursor.execute("SELECT * FROM products")
print("Products:")
for row in cursor.fetchall():
    print(row)

# Connection close karo
connection.close()

print("Database successfully created!")
