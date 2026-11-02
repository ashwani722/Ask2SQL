
import sqlite3
import ollama
import sqlglot
from sqlglot import exp
import matplotlib.pyplot as plt

DB_PATH = "file:sales.db?mode=ro"

ALLOWED_COLUMNS = {
    "products": {"product_id", "product_name", "price"},
    "orders": {"order_id", "product_id", "quantity", "order_date"},
}


def validate_sql(sql):
    try:
        statements = sqlglot.parse(sql, read="sqlite")
    except Exception as error:
        return False, f"SQL parse error: {error}"

    if len(statements) != 1 or statements[0] is None:
        return False, "Sirf ek SQL statement allowed hai."

    tree = statements[0]

    if not isinstance(tree, exp.Select):
        return False, "Sirf SELECT query allowed hai."

    if tree.args.get("into") is not None:
        return False, "SELECT INTO allowed nahi hai."

    tables = list(tree.find_all(exp.Table))

    if not tables:
        return False, "Allowed table ka use zaroori hai."

    aliases = {}

    for table in tables:
        name = table.name.lower()

        if name not in ALLOWED_COLUMNS:
            return False, f"Table '{name}' allowed nahi hai."

        if table.db or table.catalog:
            return False, "External tables allowed nahi hain."

        aliases[table.alias_or_name.lower()] = name

    for column in tree.find_all(exp.Column):
        if column.is_star:
            continue

        name = column.name.lower()

        if column.table:
            table_name = aliases.get(column.table.lower())

            if table_name is None:
                return False, f"Unknown table alias: {column.table}"

            if name not in ALLOWED_COLUMNS[table_name]:
                return False, f"Column '{name}' allowed nahi hai."
        else:
            available = set()

            for table_name in aliases.values():
                available.update(ALLOWED_COLUMNS[table_name])

            if name not in available:
                return False, f"Column '{name}' allowed nahi hai."

    return True, "Query approved."


def print_table(columns, rows):
    if not rows:
        print("Koi result nahi mila.")
        return

    widths = [
        max(len(str(columns[i])), max(len(str(row[i])) for row in rows))
        for i in range(len(columns))
    ]

    print("\n" + " | ".join(
        str(col).ljust(widths[i]) for i, col in enumerate(columns)
    ))
    print("-" * (sum(widths) + 3 * (len(widths) - 1)))

    for row in rows:
        print(" | ".join(
            str(value).ljust(widths[i]) for i, value in enumerate(row)
        ))


def create_chart(columns, rows):
    if not rows or len(columns) != 2:
        print("\nChart nahi bana: result mein exactly 2 columns hone chahiye.")
        return

    categories = [str(row[0]) for row in rows]
    values = []

    try:
        for row in rows:
            values.append(float(row[1]))
    except (TypeError, ValueError):
        print("\nChart nahi bana: second column numeric nahi hai.")
        return

    plt.figure(figsize=(9, 5))
    plt.bar(categories, values)
    plt.xlabel(columns[0])
    plt.ylabel(columns[1])
    plt.title(f"{columns[1]} by {columns[0]}")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()

    file_name = "analysis_chart.png"
    plt.savefig(file_name)
    print(f"\nChart save ho gaya: {file_name}")

    plt.show()


def main():
    question = input("Apna question likho: ").strip()

    if not question:
        print("Please question enter karo.")
        return

    prompt = f"""
You are an AI Text-to-SQL Data Analyst.

Database: SQLite

Table products:
- product_id (INTEGER)
- product_name (TEXT)
- price (REAL)

Table orders:
- order_id (INTEGER)
- product_id (INTEGER)
- quantity (INTEGER)
- order_date (TEXT)

Relationship:
products.product_id = orders.product_id

Rules:
- Generate exactly one SQLite SELECT query.
- Use only the listed tables and columns.
- Use JOIN when product names and order details are needed.
- For total quantity per product, use SUM(orders.quantity)
  and GROUP BY products.product_name.
- Return only SQL without markdown fences.

User question: {question}
"""

    try:
        response = ollama.chat(
            model="llama3.2",
            messages=[{"role": "user", "content": prompt}]
        )

        sql = response["message"]["content"].strip()
        sql = sql.replace("```sql", "").replace("```", "").strip()

        print("\nAI-generated SQL:")
        print(sql)

        approved, message = validate_sql(sql)

        if not approved:
            print("\nQuery rejected:", message)
            return

        print("\nSQL validation:", message)

        conn = sqlite3.connect(DB_PATH, uri=True)

        try:
            cursor = conn.cursor()
            cursor.execute("EXPLAIN QUERY PLAN " + sql)
            cursor.fetchall()

            cursor.execute(sql)
            rows = cursor.fetchall()

            columns = [item[0] for item in cursor.description]

            print("\nDatabase result:")
            print_table(columns, rows)

            # Chart tabhi banega jab result suitable ho
            create_chart(columns, rows)

        except sqlite3.Error as error:
            print("\nSQL execution error:", error)

        finally:
            conn.close()

    except Exception as error:
        print("\nProblem:", error)


if __name__ == "__main__":
    main()
