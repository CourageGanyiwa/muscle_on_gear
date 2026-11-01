import os

from flask import Flask, flash, render_template, request, redirect, url_for, session
from db import get_db
from datetime import datetime
import hashlib
from functools import wraps



app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")

current_date = datetime.now().strftime("%Y-%m-%d")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
@login_required
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            flash("Username and password are required", "error")
            return redirect(url_for("login"))

        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, username, password
            FROM users
            WHERE username = %s
        """, (username,))

        user = cursor.fetchone()
        cursor.close()
        db.close()

        if user and user["password"] == hashlib.sha256(password.encode()).hexdigest():
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password", "error")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    # Registration is disabled - only 3 team members allowed
    flash("Registration is disabled. Contact admin to add users.", "error")
    return redirect(url_for("login"))

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out", "success")
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    # KPI: total sales today
    cursor.execute("""
        SELECT SUM(total) AS total_sales
        FROM orders
        WHERE (status IS NULL OR status != 'cancelled')
    """)
    sales = cursor.fetchone()["total_sales"] or 0

    # KPI: total historical orders
    cursor.execute("""
        SELECT COUNT(*) AS total_orders
        FROM orders
        WHERE (status IS NULL OR status != 'cancelled')
    """)
    orders = cursor.fetchone()["total_orders"]

    print("Total sales:", sales)
    print("Total orders:", orders)

    # KPI: avg order value
    cursor.execute("""
        SELECT AVG(total) AS avg_order
        FROM orders
        WHERE (status IS NULL OR status != 'cancelled')
    """)
    avg = cursor.fetchone()["avg_order"] or 0
    avg = round(avg, 2)

    # KPI: supplier total cost for all non-cancelled orders
    cursor.execute("""
        SELECT SUM(oi.quantity * sp.cost_price) AS supplier_total
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN supplier_prices sp ON sp.product_id = oi.product_id
        WHERE (o.status IS NULL OR o.status != 'cancelled')
    """)
    supplier_total = cursor.fetchone()["supplier_total"] or 0

    # KPI: profit amount (sales minus supplier cost)
    profit_margin = round(sales - supplier_total, 2)

    # Top products
    cursor.execute("""
        SELECT 
            p.name,
            SUM(oi.quantity) AS units_sold,
            SUM(oi.quantity * oi.price) AS revenue
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id
        WHERE (o.status IS NULL OR o.status != 'cancelled')
        GROUP BY p.id, p.name
        ORDER BY units_sold DESC
    """)
    products = cursor.fetchall()

    return render_template(
        "dashboard.html",
        sales=sales,
        orders=orders,
        avg=avg,
        supplier_total=supplier_total,
        profit_margin=profit_margin,
        products=products
    )

@app.route("/orders-by-day")
@login_required
def orders_by_day():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            o.id AS order_id,
            o.order_date,
            o.total,
            o.status,
            c.name AS customer_name
        FROM orders o
        LEFT JOIN customers c ON c.id = o.customer_id
        WHERE o.status IS NULL OR o.status != 'cancelled'
        ORDER BY o.order_date DESC
    """)

    orders = cursor.fetchall()

    order_ids = [order["order_id"] for order in orders]
    order_products = {}
    order_supplier_totals = {}
    if order_ids:
        placeholders = ",".join(["%s"] * len(order_ids))

        cursor.execute(f"""
            SELECT
                oi.order_id,
                p.name AS product_name,
                oi.quantity,
                sp.cost_price AS supplier_price
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            LEFT JOIN supplier_prices sp ON sp.product_id = oi.product_id
            WHERE oi.order_id IN ({placeholders})
            ORDER BY oi.order_id
        """, tuple(order_ids))

        items = cursor.fetchall()
        for item in items:
            order_products.setdefault(item["order_id"], []).append({
                "name": item["product_name"],
                "quantity": item["quantity"],
                "supplier_price": item["supplier_price"]
            })

        cursor.execute(f"""
            SELECT
                oi.order_id,
                SUM(oi.quantity * sp.cost_price) AS supplier_total
            FROM order_items oi
            JOIN supplier_prices sp ON sp.product_id = oi.product_id
            WHERE oi.order_id IN ({placeholders})
            GROUP BY oi.order_id
        """, tuple(order_ids))

        totals = cursor.fetchall()
        for total_row in totals:
            order_supplier_totals[total_row["order_id"]] = float(total_row["supplier_total"] or 0)

    grouped = {}
    for order in orders:
        order_date = order["order_date"]
        if hasattr(order_date, "strftime"):
            date_key = order_date.strftime("%Y-%m-%d")
            order_date_str = order_date.strftime("%Y-%m-%d")
        else:
            date_key = str(order_date)[:10]
            order_date_str = str(order_date)[:10]

        order["order_date_str"] = order_date_str
        order["products"] = order_products.get(order["order_id"], [])
        order["supplier_total"] = order_supplier_totals.get(order["order_id"], 0)

        if date_key not in grouped:
            grouped[date_key] = {
                "orders": [],
                "daily_total": 0
            }

        grouped[date_key]["orders"].append(order)
        grouped[date_key]["daily_total"] += order["supplier_total"]

    day_groups = [
        {
            "date": day,
            "orders": grouped[day]["orders"],
            "daily_total": round(grouped[day]["daily_total"], 2)
        }
        for day in sorted(grouped.keys(), reverse=True)
    ]

    return render_template("daily_orders.html", day_groups=day_groups)

@app.route("/orders-by-day/export")
@login_required
def orders_by_day_export():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            o.id AS order_id,
            o.order_date,
            o.status,
            c.name AS customer_name
        FROM orders o
        LEFT JOIN customers c ON c.id = o.customer_id
        WHERE o.status IS NULL OR o.status != 'cancelled'
        ORDER BY o.order_date DESC
    """)

    orders = cursor.fetchall()
    order_ids = [order["order_id"] for order in orders]
    order_products = {}
    order_supplier_totals = {}

    if order_ids:
        placeholders = ",".join(["%s"] * len(order_ids))

        cursor.execute(f"""
            SELECT
                oi.order_id,
                p.name AS product_name,
                oi.quantity,
                sp.cost_price AS supplier_price
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            LEFT JOIN supplier_prices sp ON sp.product_id = oi.product_id
            WHERE oi.order_id IN ({placeholders})
            ORDER BY oi.order_id
        """, tuple(order_ids))

        items = cursor.fetchall()
        for item in items:
            order_products.setdefault(item["order_id"], []).append({
                "name": item["product_name"],
                "quantity": item["quantity"],
                "supplier_price": item["supplier_price"]
            })

        cursor.execute(f"""
            SELECT
                oi.order_id,
                SUM(oi.quantity * sp.cost_price) AS supplier_total
            FROM order_items oi
            JOIN supplier_prices sp ON sp.product_id = oi.product_id
            WHERE oi.order_id IN ({placeholders})
            GROUP BY oi.order_id
        """, tuple(order_ids))

        totals = cursor.fetchall()
        for total_row in totals:
            order_supplier_totals[total_row["order_id"]] = float(total_row["supplier_total"] or 0)

    lines = ["Orders by Day Report\n"]
    for order in orders:
        order_date = order["order_date"]
        if hasattr(order_date, "strftime"):
            order_date_str = order_date.strftime("%Y-%m-%d %H:%M")
        else:
            order_date_str = str(order_date)

        products = order_products.get(order["order_id"], [])
        supplier_total = order_supplier_totals.get(order["order_id"], 0)

        lines.append(f"Order #{order['order_id']}\n")
        lines.append(f"Customer: {order['customer_name'] or 'Guest'}\n")
        lines.append(f"Date / Time: {order_date_str}\n")
        lines.append(f"Supplier Total: R {supplier_total}\n")
        lines.append(f"Status: {order['status'] or 'completed'}\n")
        lines.append("Products ordered:\n")
        if products:
            for item in products:
                lines.append(f"- {item['quantity']} x {item['name']} @ R {item['supplier_price']}\n")
        else:
            lines.append("- No line items found.\n")
        lines.append("\n")

    content = "".join(lines)
    return (content, 200, {
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Disposition": "attachment; filename=orders-by-day.txt"
    })

@app.route("/create-order", methods=["GET", "POST"])
@login_required
def create_order():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # ======================
    # GET → show products
    # ======================
    if request.method == "GET":

        cursor.execute("""
            SELECT id, name
            FROM products
        """)

        products = cursor.fetchall()

        return render_template(
            "create_order.html",
            products=products,
            current_date=current_date
        )

    # ======================
    # POST → process cart
    # ======================

    customer_name = request.form["customer_name"]
    order_date = request.form.get("order_date")

    if not order_date:
        order_date = datetime.now()

    # --------------------------------
    # 1. customer lookup/create
    # --------------------------------
    cursor.execute("""
        SELECT id
        FROM customers
        WHERE name = %s
    """, (customer_name,))

    customer = cursor.fetchone()

    if customer is None:

        cursor.execute("""
            INSERT INTO customers (name)
            VALUES (%s)
        """, (customer_name,))

        customer_id = cursor.lastrowid

    else:
        customer_id = customer["id"]

    # --------------------------------
    # 2. loop products
    # --------------------------------
    cursor.execute("""
        SELECT id
        FROM products
    """)

    products = cursor.fetchall()

    total = 0
    items = []

    for p in products:

        pid = p["id"]

        selected = request.form.get(f"product_{pid}")
        qty = request.form.get(f"qty_{pid}")

        # product selected?
        if selected and qty and int(qty) > 0:

            quantity = int(qty)

            # get price
            cursor.execute("""
                SELECT price
                FROM pricing
                WHERE product_id = %s
                LIMIT 1
            """, (pid,))

            row = cursor.fetchone()

            if not row:
                continue

            price = row["price"]

            subtotal = price * quantity

            total += subtotal

            items.append((pid, quantity, price))

    # --------------------------------
    # 3. create order
    # --------------------------------
    cursor.execute("""
        INSERT INTO orders (customer_id, total, order_date, status)
        VALUES (%s, %s, %s, 'completed')
    """, (customer_id, total, order_date))

    order_id = cursor.lastrowid

    # --------------------------------
    # 4. save order items
    # --------------------------------
    for pid, qty, price in items:

        cursor.execute("""
            INSERT INTO order_items
            (order_id, product_id, quantity, price)
            VALUES (%s, %s, %s, %s)
        """, (order_id, pid, qty, price))

        # inventory update
        cursor.execute("""
            UPDATE inventory
            SET quantity = quantity - %s
            WHERE product_id = %s
        """, (qty, pid))

    db.commit()

    flash("Order created successfully")

    return redirect(url_for("dashboard"))

@app.route("/create-payment", methods=["GET","POST"])
@login_required
def create_payment():
    db = get_db()
    cursor = db.cursor(dictionary=True)


    if request.method == "GET":
    
            cursor.execute("""
                SELECT payment_date, amount, payment_type
                FROM payments
            """)
    
            payments = cursor.fetchall()
    
            return render_template(
                "create_payment.html",
                payments=payments,
                current_date=current_date
            )
         
    amount = request.form["amount"]
    type_of_payment = request.form["payment_type"]
    payment_type = type_of_payment.capitalize()
    payment_date = request.form.get("date")

    if not payment_date:
        payment_date = datetime.now()

    cursor.execute("""
            INSERT INTO payments (payment_date, amount, payment_type)
            VALUES (%s, %s, %s)
        """, (payment_date,amount, payment_type))
    
    db.commit()

    flash("Payment made successfully", "success")

    return redirect(request.referrer)
    
    

@app.route("/add-customer", methods=["GET", "POST"])
def add_customer():
    db = get_db()
    cursor = db.cursor()

    if request.method == "POST":
        name = request.form["name"]
        phone = request.form["phone"]
        email = request.form["email"]

        cursor.execute("""
            INSERT INTO customers (name, phone, email)
            VALUES (%s, %s, %s)
        """, (name, phone, email))

        db.commit()

        return redirect("/add-customer")

    return render_template("add_customer.html")

@app.route("/inventory", methods=["GET", "POST"])
@login_required
def inventory():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # ======================
    # POST → update stock
    # ======================
    if request.method == "POST":

        product_id = request.form["product_id"]
        change_qty = int(request.form["change_qty"])
        reason = request.form["reason"]

        cursor.execute("""
            INSERT INTO inventory (product_id, quantity)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE quantity = quantity + VALUES(quantity)
        """, (product_id, change_qty))

        db.commit()

        return redirect(url_for("inventory"))

    # ======================
    # GET → show products + stock
    # ======================
    cursor.execute("""
        SELECT p.id, p.name, i.quantity
        FROM products p
        LEFT JOIN inventory i ON i.product_id = p.id
    """)
    products = cursor.fetchall()

    return render_template("inventory.html", products=products)

if __name__ == "__main__":
    app.run(host="127.0.0.1",port=5001,debug=True)