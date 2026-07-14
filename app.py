import os
import sqlite3
from datetime import datetime

from flask import Flask, render_template, request, redirect, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash

from blockchain import Blockchain
from roles import ROLES, DB_MANAGED_ROLES, ADMIN_USERNAME, ADMIN_PASSWORD_HASH
from utils import generate_qr_code
from database import init_db, DB_NAME

app = Flask(__name__)
# Secret key comes from the environment in production; a random fallback is
# used for local dev so sessions still work without extra setup.
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

bc = Blockchain()
init_db()


def get_db():
    return sqlite3.connect(DB_NAME)


def product_exists(product_id):
    return any(b.data.get("product_id") == product_id for b in bc.chain)


@app.route("/", methods=["GET", "POST"])
def login():
    # Already logged in? Skip straight to the dashboard.
    if "role" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        role = request.form.get("role", "")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        authenticated = False

        if role == "Admin":
            if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
                authenticated = True
        elif role in DB_MANAGED_ROLES:
            conn = get_db()
            row = conn.execute(
                "SELECT password FROM users WHERE username=? AND role=?",
                (username, role),
            ).fetchone()
            conn.close()
            if row and check_password_hash(row[0], password):
                authenticated = True

        if authenticated:
            session["role"] = role
            session["username"] = username
            return redirect(url_for("dashboard"))

        flash("Invalid credentials")

    return render_template("login.html", roles=ROLES)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if "role" not in session:
        return redirect(url_for("login"))

    role = session["role"]
    context = {"role": role}

    if role == "Admin":
        context["stats"] = bc.get_stats()

    elif role == "Manufacturer":
        products = sorted(bc.get_all_products().values(), key=lambda p: p["created_at"], reverse=True)
        context["products"] = products
        context["total"] = len(products)

    elif role == "Distributor":
        all_products = list(bc.get_all_products().values())
        pending = sorted(
            [p for p in all_products if p["status"] == "Manufactured"],
            key=lambda p: p["created_at"],
        )
        distributed = sorted(
            [p for p in all_products if p["distributed"]],
            key=lambda p: p["updated_at"],
            reverse=True,
        )
        in_transit_count = sum(1 for p in all_products if p["status"] == "In Transit")
        context.update(
            pending=pending,
            distributed=distributed,
            pending_count=len(pending),
            distributed_count=len(distributed),
            in_transit_count=in_transit_count,
        )

    elif role == "Retailer":
        all_products = list(bc.get_all_products().values())
        pending = sorted(
            [p for p in all_products if p["status"] == "In Transit"],
            key=lambda p: p["updated_at"],
        )
        completed = sorted(
            [p for p in all_products if p["status"] in ("Delivered", "Sold")],
            key=lambda p: p["updated_at"],
            reverse=True,
        )
        context.update(
            pending=pending,
            completed=completed,
            pending_count=len(pending),
            completed_count=len(completed),
        )

    return render_template("dashboard.html", **context)


@app.route("/produce_product", methods=["GET", "POST"])
def produce_product():
    # Manufacturer-only: creates a brand new product on the chain.
    if session.get("role") != "Manufacturer":
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        product_id = request.form.get("product_id", "").strip()
        description = request.form.get("description", "").strip()

        if not product_id:
            flash("Product ID is required")
        elif product_exists(product_id):
            flash("A product with this ID already exists")
        else:
            bc.add_block({
                "product_id": product_id,
                "description": description,
                "status": "Manufactured",
                "by": session["role"],
            })
            flash("Product produced")
            return redirect(url_for("dashboard"))

    return render_template("produce_product.html")


@app.route("/distribute_product", methods=["GET", "POST"])
def distribute_product():
    # Distributor-only: moves an existing product through the supply chain.
    if session.get("role") != "Distributor":
        return redirect(url_for("dashboard"))

    # Dashboard quick-action icons (Packing / Shipping / In Transit) link
    # here with ?status=... to pre-select the right option in the form.
    preselect_status = request.args.get("status", "")

    if request.method == "POST":
        product_id = request.form.get("product_id", "").strip()
        status = request.form.get("status", "")
        description = request.form.get("description", "").strip()

        if not product_id:
            flash("Product ID is required")
        elif not product_exists(product_id):
            flash("No product found with that ID. Ask the manufacturer to produce it first.")
        else:
            bc.add_block({
                "product_id": product_id,
                "description": description or f"Distribution update: {status}",
                "status": status,
                "by": session["role"],
            })
            flash("Distribution status updated")
            return redirect(url_for("dashboard"))

    return render_template("distribute_product.html", preselect_status=preselect_status)


@app.route("/update_status", methods=["GET", "POST"])
def update_status():
    # Retailer-only: marks delivery / sale status on an existing product.
    if session.get("role") != "Retailer":
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        product_id = request.form.get("product_id", "").strip()
        status = request.form.get("status", "")
        description = request.form.get("description", "").strip()

        if not product_id:
            flash("Product ID is required")
        elif not product_exists(product_id):
            flash("No product found with that ID.")
        else:
            bc.add_block({
                "product_id": product_id,
                "description": description or f"Retail update: {status}",
                "status": status,
                "by": session["role"],
            })
            flash("Product status updated")
            return redirect(url_for("dashboard"))

    return render_template("update_status.html")


@app.route("/add_user", methods=["GET", "POST"])
def add_user():
    if session.get("role") != "Admin":
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "")

        if not username or not password or role not in DB_MANAGED_ROLES:
            flash("Please provide a valid username, password and role")
        else:
            conn = get_db()
            try:
                conn.execute(
                    "INSERT INTO users(username,password,role) VALUES(?,?,?)",
                    (username, generate_password_hash(password), role),
                )
                conn.commit()
                flash("User added")
            except sqlite3.IntegrityError:
                flash("That username already exists for this role")
            finally:
                conn.close()

    return render_template("add_user.html", roles=DB_MANAGED_ROLES)


@app.route("/view_users")
def view_users():
    if session.get("role") != "Admin":
        return redirect(url_for("dashboard"))
    conn = get_db()
    users = conn.execute("SELECT id,username,role FROM users").fetchall()
    conn.close()
    return render_template("view_users.html", users=users)


@app.route("/delete_user/<int:uid>")
def delete_user(uid):
    if session.get("role") != "Admin":
        return redirect(url_for("dashboard"))
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    conn.close()
    flash("User deleted")
    return redirect(url_for("view_users"))


@app.route("/product_history")
def product_history():
    # Admin-only: hub with per-stage icons (Manufacturer / Distributor /
    # Retailer) and a default view that only lists products whose full
    # lifecycle (all three stages) is complete.
    if session.get("role") != "Admin":
        return redirect(url_for("dashboard"))

    stage = request.args.get("stage", "completed")
    products = list(bc.get_all_products().values())

    if stage == "manufacturer":
        rows = [p for p in products if p["manufactured"]]
        heading = "All Manufactured Products"
    elif stage == "distributor":
        rows = [p for p in products if p["distributed"]]
        heading = "All Distributed Products"
    elif stage == "retailer":
        rows = [p for p in products if p["retailed"]]
        heading = "All Products Reached Retailer"
    else:
        stage = "completed"
        rows = [p for p in products if p["manufactured"] and p["distributed"] and p["retailed"]]
        heading = "Completed Products (Full Lifecycle)"

    rows.sort(key=lambda p: p["updated_at"], reverse=True)

    counts = {
        "manufacturer": sum(1 for p in products if p["manufactured"]),
        "distributor": sum(1 for p in products if p["distributed"]),
        "retailer": sum(1 for p in products if p["retailed"]),
        "completed": sum(1 for p in products if p["manufactured"] and p["distributed"] and p["retailed"]),
    }

    return render_template(
        "product_history.html", rows=rows, heading=heading, stage=stage, counts=counts
    )


@app.route("/track", methods=["GET", "POST"])
def track():
    # Admin-only "deep dive": search one product and see its full block-by-block trail.
    if session.get("role") != "Admin":
        return redirect(url_for("dashboard"))

    pid = None
    if request.method == "POST":
        pid = request.form.get("product_id", "").strip()
    elif request.args.get("product_id"):
        pid = request.args.get("product_id", "").strip()

    if pid:
        history = bc.get_product_history(pid)
        qr = generate_qr_code(pid) if history else None
        return render_template("view_history.html", history=history, pid=pid, qr=qr)

    return render_template("track_product.html")


@app.route("/verify_chain")
def verify_chain():
    # Admin-only: integrity check, part of the reporting toolkit.
    if session.get("role") != "Admin":
        return redirect(url_for("dashboard"))
    flash("Blockchain Valid" if bc.validate_chain() else "Blockchain Tampered")
    return redirect(url_for("dashboard"))


@app.route("/admin")
def admin():
    if session.get("role") != "Admin":
        return redirect(url_for("dashboard"))
    return render_template("admin.html", chain=bc.chain, stats=bc.get_stats())


@app.template_filter("datetimeformat")
def datetimeformat(value, fmt="%Y-%m-%d %H:%M:%S"):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).strftime(fmt)
    return value


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode)
