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
        WHERE DATE(order_date) = CURDATE()
        AND status != 'cancelled'
    """)
    sales = cursor.fetchone()["total_sales"] or 0

    # KPI: orders today
    cursor.execute("""
        SELECT COUNT(*) AS total_orders
        FROM orders
        WHERE DATE(order_date) = CURDATE()
        AND status != 'cancelled'
    """)
    orders = cursor.fetchone()["total_orders"]

    # KPI: avg order value
    cursor.execute("""
        SELECT AVG(total) AS avg_order
        FROM orders
        WHERE DATE(order_date) = CURDATE()
    """)
    avg = cursor.fetchone()["avg_order"] or 0
    avg = round(avg, 2)

    # Top products
    cursor.execute("""
        SELECT 
            p.name,
            SUM(oi.quantity) AS units_sold,
            SUM(oi.quantity * oi.price) AS revenue
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id
        WHERE DATE(o.order_date) = CURDATE()
        GROUP BY p.id, p.name
        ORDER BY units_sold DESC
    """)
    products = cursor.fetchall()

    return render_template(
        "dashboard.html",
        sales=sales,
        orders=orders,
        avg=avg,
        products=products
    )

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
        INSERT INTO orders (customer_id, total, order_date)
        VALUES (%s, %s, %s)
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

        # increase or decrease stock
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
    app.run(debug=True)