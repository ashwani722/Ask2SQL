import sqlite3

connection = sqlite3.connect("sales.db")

query = """
SELECT
    products.product_name,
    SUM(orders.quantity) AS total_quantity
FROM products
INNER JOIN orders
    ON products.product_id = orders.product_id
GROUP BY products.product_id, products.product_name;
"""

try:
    cursor = connection.execute(query)

    print("Query successful!")
    print("Product Name | Total Quantity")

    for row in cursor.fetchall():
        print(row)

except sqlite3.Error as error:
    print("Database error:", error)

finally:
    connection.close()