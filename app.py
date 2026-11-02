import sqlite3
import re
import io
import os
import pandas as pd
import streamlit as st
import ollama
import sqlglot
import matplotlib.pyplot as plt
from datetime import date, timedelta

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(
    page_title="AI Sales Data Analyst",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "sales.db"
)

MODEL_NAME = "llama3.2"

# =========================
# STYLING
# =========================
st.markdown("""
<style>
.stApp {
    background: var(--background-color);
}

.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
}

.dashboard-title {
    font-size: 2.25rem;
    font-weight: 800;
    margin-bottom: 0.2rem;
}

.dashboard-subtitle {
    color: var(--text-color);
    opacity: 0.7;
    margin-bottom: 1.5rem;
}

div[data-testid="stMetric"] {
    background: var(--secondary-background-color);
    padding: 18px;
    border-radius: 14px;
    border: 1px solid rgba(128,128,128,0.2);
}

/* Purple Analyze Question button */
div.stButton > button[kind="primary"] {
    width: 100%;
    min-height: 46px;
    border-radius: 10px;
    font-weight: 700;
    background: #7C3AED;
    color: white;
    border: 1px solid #7C3AED;
}

div.stButton > button[kind="primary"]:hover {
    background: #6D28D9;
    border-color: #6D28D9;
    color: white;
}
</style>
""", unsafe_allow_html=True)


# =========================
# DATABASE
# =========================
def get_connection(read_only=True):
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(
            f"Database nahi mili: {DB_PATH}"
        )

    conn = sqlite3.connect(DB_PATH)

    if read_only:
        conn.execute("PRAGMA query_only = ON")

    return conn


def read_sql(query, params=()):
    conn = get_connection()

    try:
        return pd.read_sql_query(
            query,
            conn,
            params=params
        )
    finally:
        conn.close()


@st.cache_data
def get_table_columns(table_name):
    allowed = {"products", "orders"}

    if table_name not in allowed:
        return []

    conn = get_connection()

    try:
        rows = conn.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()

        return [row[1] for row in rows]
    finally:
        conn.close()


def check_database():
    product_columns = get_table_columns("products")
    order_columns = get_table_columns("orders")

    if not product_columns or not order_columns:
        st.error(
            "Database mein products ya orders table nahi mili. "
            "sales.db aur table names check karo."
        )
        st.stop()

    required_products = {
        "product_id",
        "product_name",
        "price"
    }

    required_orders = {
        "order_id",
        "product_id",
        "quantity",
        "order_date"
    }

    if not required_products.issubset(product_columns):
        st.error(
            "products table ke columns expected format se match nahi karte."
        )
        st.stop()

    if not required_orders.issubset(order_columns):
        st.error(
            "orders table ke columns expected format se match nahi karte."
        )
        st.stop()


# =========================
# PERMANENT QUERY HISTORY
# =========================
def init_query_history():
    """
    Query history table ko create karta hai agar
    woh pehle se database mein maujood nahi hai.
    Existing sales tables ko change nahi karta.
    """
    conn = get_connection(read_only=False)

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS query_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                sql_query TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL DEFAULT (
                    datetime('now', 'localtime')
                )
            )
        """)

        conn.commit()
    finally:
        conn.close()


def save_query_history(
    question,
    sql_query,
    status,
    error_message=None
):
    """
    User ka question, generated SQL, result status
    aur error ko permanently save karta hai.
    """
    conn = get_connection(read_only=False)

    try:
        conn.execute("""
            INSERT INTO query_history (
                question,
                sql_query,
                status,
                error_message
            )
            VALUES (?, ?, ?, ?)
        """, (
            question,
            sql_query,
            status,
            error_message
        ))

        conn.commit()
    finally:
        conn.close()


def get_query_history(limit=50):
    """
    Latest saved query attempts return karta hai.
    """
    return read_sql("""
        SELECT
            id,
            question,
            sql_query,
            status,
            error_message,
            created_at
        FROM query_history
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))


# =========================
# SALES DATA
# =========================
@st.cache_data
def load_sales_data():
    return read_sql("""
        SELECT
            o.order_id,
            o.product_id,
            p.product_name,
            p.price,
            o.quantity,
            o.order_date,
            (p.price * o.quantity) AS revenue
        FROM orders o
        JOIN products p
            ON o.product_id = p.product_id
    """)


def apply_filters(
    data,
    selected_product,
    start_date,
    end_date
):
    filtered = data.copy()

    if selected_product != "All Products":
        filtered = filtered[
            filtered["product_name"] == selected_product
        ]

    parsed_dates = pd.to_datetime(
        filtered["order_date"],
        errors="coerce"
    )

    mask = (
        parsed_dates.notna()
        & (parsed_dates.dt.date >= start_date)
        & (parsed_dates.dt.date <= end_date)
    )

    return filtered.loc[mask].copy()


def format_currency(value):
    return f"₹{value:,.2f}"


# =========================
# SALES CHARTS
# =========================
def show_sales_charts(data):
    if data.empty:
        st.info(
            "Selected filters ke liye data nahi mila."
        )
        return

    left, right = st.columns(2)

    with left:
        st.subheader("💰 Revenue by Product")

        revenue = (
            data.groupby(
                "product_name",
                as_index=False
            )["revenue"]
            .sum()
            .sort_values(
                "revenue",
                ascending=False
            )
        )

        fig, ax = plt.subplots(figsize=(7, 4))

        ax.bar(
            revenue["product_name"],
            revenue["revenue"]
        )

        ax.set_ylabel("Revenue (₹)")
        ax.set_xlabel("Product")
        ax.tick_params(
            axis="x",
            rotation=20
        )

        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

    with right:
        st.subheader("📦 Quantity Sold by Product")

        quantity = (
            data.groupby(
                "product_name",
                as_index=False
            )["quantity"]
            .sum()
            .sort_values(
                "quantity",
                ascending=False
            )
        )

        fig, ax = plt.subplots(figsize=(7, 4))

        ax.bar(
            quantity["product_name"],
            quantity["quantity"]
        )

        ax.set_ylabel("Units Sold")
        ax.set_xlabel("Product")
        ax.tick_params(
            axis="x",
            rotation=20
        )

        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

    st.subheader("📈 Revenue Trend by Date")

    trend_data = data.copy()

    trend_data["parsed_date"] = pd.to_datetime(
        trend_data["order_date"],
        errors="coerce"
    )

    trend_data = trend_data.dropna(
        subset=["parsed_date"]
    )

    if not trend_data.empty:
        trend = (
            trend_data.groupby(
                trend_data["parsed_date"].dt.date
            )["revenue"]
            .sum()
            .sort_index()
        )

        fig, ax = plt.subplots(figsize=(11, 4))

        ax.plot(
            [str(day) for day in trend.index],
            trend.values,
            marker="o"
        )

        ax.set_ylabel("Revenue (₹)")
        ax.set_xlabel("Order Date")
        ax.tick_params(
            axis="x",
            rotation=35
        )

        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)
    else:
        st.info(
            "Valid order dates nahi hain, isliye trend nahi dikh sakta."
        )
        
# =========================
# AI TEXT-TO-SQL
# =========================
def generate_sql(
    question,
    correction_error=None,
    previous_sql=None
):
    schema = """
    Table: products
      product_id INTEGER
      product_name TEXT
      price REAL

    Table: orders
      order_id INTEGER
      product_id INTEGER
      quantity INTEGER
      order_date TEXT

    Join: products.product_id = orders.product_id
    Revenue: products.price * orders.quantity
    """

    repair_instructions = ""

    if correction_error:
        repair_instructions = f"""
        Previous SQL:
        {previous_sql}

        Error:
        {correction_error}

        Fix the SQL query based on the error.
        """

    prompt = f"""
You are an expert SQLite SQL analyst.

Database schema:
{schema}

Rules:
- Return exactly one SQLite SELECT query.
- Only use products and orders tables.
- Do not return markdown or code fences.
- Never use INSERT, UPDATE, DELETE, DROP, ALTER,
  ATTACH, DETACH, PRAGMA, CREATE, REPLACE,
  or multiple statements.
- Use valid column names from the schema.
- Use explicit JOIN conditions when needed.
- For revenue use products.price * orders.quantity.
- The order_date column stores dates as text.
- Use LIMIT 100 for detailed rows unless a smaller
  limit is requested.
- Do not invent tables or columns.

Question: {question}

{repair_instructions}

Return only SQL.
"""

    response = ollama.generate(
        model=MODEL_NAME,
        prompt=prompt
    )

    sql = response["response"].strip()

    sql = re.sub(
        r"^```(?:sql)?\s*",
        "",
        sql,
        flags=re.IGNORECASE
    )

    sql = re.sub(
        r"\s*```$",
        "",
        sql
    )

    return sql.strip()


def validate_sql(sql):
    if not sql or not sql.strip():
        raise ValueError(
            "AI ne empty SQL query return ki."
        )

    statements = sqlglot.parse(
        sql,
        read="sqlite"
    )

    if len(statements) != 1 or statements[0] is None:
        raise ValueError(
            "Sirf ek SQL statement allowed hai."
        )

    parsed = statements[0]

    if parsed.key.upper() != "SELECT":
        raise ValueError(
            "Sirf SELECT queries allowed hain."
        )

    forbidden = {
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "CREATE",
        "REPLACE",
        "ATTACH",
        "DETACH",
        "PRAGMA",
        "TRUNCATE",
        "MERGE",
        "COMMAND"
    }

    for node in parsed.walk():
        if node.key.upper() in forbidden:
            raise ValueError(
                f"Restricted SQL operation: {node.key}"
            )

    for table in parsed.find_all(sqlglot.exp.Table):
        if table.name.lower() not in {
            "products",
            "orders"
        }:
            raise ValueError(
                f"Unknown table allowed nahi hai: {table.name}"
            )

    return parsed.sql(dialect="sqlite")


def run_read_only_query(sql):
    conn = get_connection()

    try:
        conn.execute("PRAGMA query_only = ON")

        return pd.read_sql_query(
            sql,
            conn
        )
    finally:
        conn.close()


def analyze_question(question):
    previous_sql = None
    correction_error = None

    for attempt in range(2):
        try:
            sql = generate_sql(
                question,
                correction_error=correction_error,
                previous_sql=previous_sql
            )

            sql = validate_sql(sql)
            result = run_read_only_query(sql)

            return sql, result, None

        except Exception as exc:
            correction_error = str(exc)
            previous_sql = locals().get("sql")

            if attempt == 1:
                return (
                    previous_sql,
                    None,
                    correction_error
                )

    return None, None, "Query complete nahi hui."


def generate_insights(question, sql, result):
    if result is None or result.empty:
        return "Is question ke liye koi result nahi mila."

    preview = result.head(10).to_string(
        index=False
    )

    prompt = f"""
You are a sales data analyst.
Explain the query result in simple Hinglish.
Give 2-4 short useful observations.
Do not invent numbers or facts not shown in the result.

Question: {question}
SQL: {sql}

Result:
{preview}
"""

    response = ollama.generate(
        model=MODEL_NAME,
        prompt=prompt
    )

    return response["response"].strip()


# =========================
# SESSION STATE
# =========================
if "question_input" not in st.session_state:
    st.session_state.question_input = ""

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

if "last_insights" not in st.session_state:
    st.session_state.last_insights = None


def set_example_question(question):
    st.session_state.question_input = question


# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.title("📊 AI Data Analyst")
    st.caption("Sales intelligence powered by AI")
    st.divider()

    check_database()

    try:
        init_query_history()
        all_sales = load_sales_data()
    except Exception as exc:
        st.error(
            f"Database load error: {exc}"
        )
        st.stop()

    st.subheader("🔎 Dashboard Filters")

    products = ["All Products"] + sorted(
        all_sales["product_name"]
        .dropna()
        .unique()
        .tolist()
    )

    selected_product = st.selectbox(
        "Select Product",
        products,
        key="product_filter"
    )

    valid_dates = pd.to_datetime(
        all_sales["order_date"],
        errors="coerce"
    ).dropna()

    if not valid_dates.empty:
        min_date = valid_dates.min().date()
        max_date = valid_dates.max().date()
    else:
        min_date = date.today() - timedelta(days=30)
        max_date = date.today()

    date_range = st.date_input(
        "Select Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        key="date_filter"
    )

    if isinstance(date_range, (tuple, list)):
        if len(date_range) == 2:
            start_date, end_date = date_range
        elif len(date_range) == 1:
            start_date = end_date = date_range[0]
        else:
            start_date, end_date = min_date, max_date
    else:
        start_date = end_date = date_range

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    st.divider()
    st.caption("Model: Llama 3.2")
    st.caption("Database: sales.db")


# =========================
# MAIN DASHBOARD
# =========================
st.markdown(
    '<div class="dashboard-title">'
    '📊 Professional Sales Dashboard'
    '</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="dashboard-subtitle">'
    'Monitor sales performance and ask questions in natural language.'
    '</div>',
    unsafe_allow_html=True
)

filtered_data = apply_filters(
    all_sales,
    selected_product,
    start_date,
    end_date
)

# KPI CARDS
total_revenue = filtered_data["revenue"].sum()
total_orders = filtered_data["order_id"].nunique()
total_quantity = filtered_data["quantity"].sum()
products_sold = filtered_data["product_name"].nunique()

st.subheader("📌 Key Performance Indicators")

k1, k2, k3, k4 = st.columns(4)

k1.metric(
    "💰 Total Revenue",
    format_currency(total_revenue)
)

k2.metric(
    "🧾 Total Orders",
    f"{total_orders:,}"
)

k3.metric(
    "📦 Units Sold",
    f"{total_quantity:,.0f}"
)

k4.metric(
    "🏷️ Products Sold",
    f"{products_sold:,}"
)

st.caption(
    f"Filters: {selected_product} | "
    f"{start_date} to {end_date}"
)

# TOP PRODUCT
if not filtered_data.empty:
    product_summary = (
        filtered_data.groupby("product_name")["quantity"]
        .sum()
        .sort_values(ascending=False)
    )

    top_product = product_summary.index[0]
    top_quantity = product_summary.iloc[0]

    st.success(
        f"🏆 Top-selling product: **{top_product}** "
        f"with **{top_quantity:,.0f} units sold** "
        f"in the selected data."
    )

st.divider()

# CHARTS
st.header("📈 Sales Analytics")
show_sales_charts(filtered_data)

# RECENT ORDERS
st.subheader("🧾 Recent Orders")

if filtered_data.empty:
    st.info(
        "Selected filters ke liye orders nahi mile."
    )
else:
    recent = filtered_data.copy()

    recent["sort_date"] = pd.to_datetime(
        recent["order_date"],
        errors="coerce"
    )

    recent = recent.sort_values(
        "sort_date",
        ascending=False,
        na_position="last"
    )

    display_columns = [
        "order_id",
        "product_name",
        "quantity",
        "price",
        "order_date",
        "revenue"
    ]

    recent_display = recent[
        display_columns
    ].head(20).copy()

    recent_display = recent_display.rename(
        columns={
            "order_id": "Order ID",
            "product_name": "Product",
            "quantity": "Quantity",
            "price": "Unit Price",
            "order_date": "Order Date",
            "revenue": "Revenue"
        }
    )

    st.dataframe(
        recent_display,
        use_container_width=True,
        hide_index=True
    )

    csv_bytes = filtered_data.to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(
        "📥 Download Filtered Sales CSV",
        data=csv_bytes,
        file_name="filtered_sales.csv",
        mime="text/csv"
    )

st.divider()

# =========================
# AI TEXT-TO-SQL ANALYST
# =========================
st.header("🤖 Ask Your Data")

st.write(
    "Apna question normal language mein likho. "
    "AI SQL query banayega aur database se result laayega."
)

examples = [
    "Show total quantity sold for each product",
    "Which product generated the highest revenue?",
    "Show total revenue by product",
    "Show the 5 most recent orders"
]

example_columns = st.columns(2)

for index, example in enumerate(examples):
    with example_columns[index % 2]:
        st.button(
            example,
            key=f"example_{index}",
            on_click=set_example_question,
            args=(example,),
            use_container_width=True
        )

question = st.text_area(
    "Your question",
    key="question_input",
    placeholder="Example: Which product sold the most?",
    height=100
)

if st.button(
    "🚀 Analyze Question",
    type="primary",
    use_container_width=True
):
    if not question.strip():
        st.warning(
            "Pehle apna question enter karo."
        )
    else:
        with st.spinner(
            "AI SQL generate aur execute kar raha hai..."
        ):
            sql, result, error = analyze_question(
                question
            )

        # Save every analysis attempt to permanent history.
        try:
            save_query_history(
                question=question.strip(),
                sql_query=sql or "",
                status="Failed" if error else "Success",
                error_message=error
            )
        except Exception as history_error:
            st.warning(
                "Query history save nahi ho paayi: "
                f"{history_error}"
            )

        if error:
            st.error(
                f"Analysis failed: {error}"
            )

            if sql:
                st.code(
                    sql,
                    language="sql"
                )
        else:
            st.session_state.analysis_result = {
                "question": question,
                "sql": sql,
                "result": result
            }

            st.session_state.last_insights = None


# =========================
# DISPLAY AI RESULTS
# =========================
if st.session_state.analysis_result:
    analysis = st.session_state.analysis_result

    st.subheader("🧠 Generated SQL")

    st.code(
        analysis["sql"],
        language="sql"
    )

    st.subheader("📋 Query Results")

    st.dataframe(
        analysis["result"],
        use_container_width=True,
        hide_index=True
    )

    result_csv = analysis["result"].to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(
        "📥 Download Query Results CSV",
        data=result_csv,
        file_name="query_results.csv",
        mime="text/csv",
        key="download_query_csv"
    )

    # =========================
    # QUERY RESULT CHART
    # =========================
    result_data = analysis["result"]

    if not result_data.empty:
        numeric_columns = (
            result_data
            .select_dtypes(include="number")
            .columns.tolist()
        )

        if numeric_columns:
            st.subheader("📊 Query Result Chart")

            label_columns = [
                column
                for column in result_data.columns
                if column not in numeric_columns
            ]

            value_column = st.selectbox(
                "Chart metric",
                numeric_columns,
                key="query_chart_metric"
            )

            chart_data = result_data.copy()

            if label_columns:
                label_column = label_columns[0]

                chart_data = chart_data.set_index(
                    label_column
                )

                chart_series = chart_data[value_column]
                x_label = label_column
            else:
                chart_series = (
                    result_data[value_column]
                    .reset_index(drop=True)
                )

                chart_series.index = [
                    f"Result {i + 1}"
                    for i in range(len(chart_series))
                ]

                x_label = "Result"

            st.bar_chart(chart_series)

            fig, ax = plt.subplots(figsize=(9, 4))

            chart_series.plot(
                kind="bar",
                ax=ax
            )

            ax.set_ylabel(value_column)
            ax.set_xlabel(x_label)
            ax.tick_params(
                axis="x",
                rotation=20
            )

            fig.tight_layout()

            image_buffer = io.BytesIO()

            fig.savefig(
                image_buffer,
                format="png",
                bbox_inches="tight"
            )

            plt.close(fig)

            st.download_button(
                "🖼️ Download Chart PNG",
                data=image_buffer.getvalue(),
                file_name="query_chart.png",
                mime="image/png",
                key="download_query_chart_png"
            )
        else:
            st.info(
                "Is query result mein numeric column nahi hai, "
                "isliye chart available nahi hai."
            )

    # =========================
    # AI INSIGHTS
    # =========================
    if st.button(
        "✨ Generate AI Insights",
        key="generate_insights"
    ):
        with st.spinner(
            "AI result analyze kar raha hai..."
        ):
            try:
                insights = generate_insights(
                    analysis["question"],
                    analysis["sql"],
                    analysis["result"]
                )

                st.session_state.last_insights = insights

            except Exception as exc:
                st.error(
                    f"Insights generate nahi hue: {exc}"
                )

    if st.session_state.last_insights:
        st.subheader("✨ AI Insights")
        st.write(
            st.session_state.last_insights
        )


# ============================
# PERMANENT QUERY HISTORY UI
# ============================
st.divider()
st.header("🕘 Query History")
st.caption(
    "Tumhare latest 50 AI analysis attempts yahan permanently saved rahenge."
)

try:
    history_data = get_query_history(limit=50)

    if history_data.empty:
        st.info(
            "Abhi koi query history nahi hai. "
            "Pehla question analyze karne ke baad yahan dikhega."
        )
    else:
        total_saved = len(history_data)

        successful_queries = int(
            (history_data["status"] == "Success").sum()
        )

        failed_queries = int(
            (history_data["status"] == "Failed").sum()
        )

        h1, h2, h3 = st.columns(3)

        h1.metric(
            "📚 Saved Attempts",
            total_saved
        )

        h2.metric(
            "✅ Successful",
            successful_queries
        )

        h3.metric(
            "❌ Failed",
            failed_queries
        )

        # ============================
        # HISTORY TABLE
        # ============================
        st.subheader("📋 Saved Questions")

        history_display = history_data[
            ["id", "created_at", "question", "status"]
        ].copy()

        history_display = history_display.rename(
            columns={
                "id": "ID",
                "created_at": "Date & Time",
                "question": "Question",
                "status": "Status",
            }
        )

        st.dataframe(
            history_display,
            use_container_width=True,
            hide_index=True,
        )

        # ============================
        # VIEW AND RERUN HISTORY
        # ============================
        st.subheader("🔍 View and Rerun Previous Queries")

        for _, history_row in history_data.iterrows():
            history_id = int(history_row["id"])
            history_status = str(history_row["status"])
            history_question = str(history_row["question"])
            history_time = str(history_row["created_at"])

            status_icon = (
                "✅" if history_status == "Success" else "❌"
            )

            expander_title = (
                f"{status_icon} #{history_id} — "
                f"{history_question[:70]} ({history_time})"
            )

            with st.expander(expander_title):
                st.markdown("**Question:**")
                st.write(history_question)

                st.markdown("**Date & Time:**")
                st.write(history_time)

                st.markdown("**Status:**")
                st.write(history_status)

                saved_sql = history_row["sql_query"]

                st.markdown("**Generated SQL:**")

                if isinstance(saved_sql, str) and saved_sql.strip():
                    st.code(
                        saved_sql,
                        language="sql"
                    )

                    if st.button(
                        "🔄 Run Again",
                        key=f"rerun_history_{history_id}",
                    ):
                        try:
                            # Validate again before execution.
                            safe_sql = validate_sql(saved_sql)

                            rerun_result = run_read_only_query(
                                safe_sql
                            )

                            # Save rerun as a new history attempt.
                            save_query_history(
                                question=history_question,
                                sql_query=safe_sql,
                                status="Success",
                                error_message=None,
                            )

                            st.success(
                                "Query successfully execute hui!"
                            )

                            st.markdown("**New Result:**")

                            if rerun_result.empty:
                                st.info(
                                    "Query execute hui, lekin koi row nahi mili."
                                )
                            else:
                                st.dataframe(
                                    rerun_result,
                                    use_container_width=True,
                                    hide_index=True,
                                )

                                result_csv = rerun_result.to_csv(
                                    index=False
                                ).encode("utf-8")

                                st.download_button(
                                    "📥 Download Result CSV",
                                    data=result_csv,
                                    file_name=f"query_result_{history_id}.csv",
                                    mime="text/csv",
                                    key=f"rerun_csv_{history_id}",
                                )

                        except Exception as rerun_error:
                            error_text = str(rerun_error)

                            try:
                                save_query_history(
                                    question=history_question,
                                    sql_query=saved_sql,
                                    status="Failed",
                                    error_message=error_text,
                                )
                            except Exception as save_error:
                                st.warning(
                                    "Rerun error history save nahi hui: "
                                    f"{save_error}"
                                )

                            st.error(
                                "Query dobara run nahi ho paayi: "
                                f"{error_text}"
                            )
                else:
                    st.info(
                        "Is attempt ke liye SQL query save nahi hui."
                    )

                # ============================
                # ERROR DETAILS
                # ============================
                saved_error = history_row["error_message"]

                if isinstance(saved_error, str) and saved_error.strip():
                    st.markdown("**Error Details:**")
                    st.error(saved_error)

        # ============================
        # EXPORT HISTORY
        # ============================
        st.divider()

        history_csv = history_data.to_csv(
            index=False
        ).encode("utf-8")

        st.download_button(
            "📥 Download Query History CSV",
            data=history_csv,
            file_name="query_history.csv",
            mime="text/csv",
            key="download_query_history_csv",
        )

except Exception as history_error:
    st.warning(
        f"Query history load nahi ho paayi: {history_error}"
    )


# =========================
# FOOTER
# =========================
st.divider()

st.caption(
    "Note: Revenue is calculated as unit price × quantity. "
    "Discounts, returns, and taxes are not included unless recorded "
    "separately in the database."
)