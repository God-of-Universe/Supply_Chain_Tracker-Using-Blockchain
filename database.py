import sqlite3
from werkzeug.security import generate_password_hash

DB_NAME = "supply_chain.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS blocks(
        idx INTEGER,
        timestamp REAL,
        product_id TEXT,
        description TEXT,
        status TEXT,
        role TEXT,
        prev_hash TEXT,
        hash TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        password TEXT,
        role TEXT,
        UNIQUE(username, role))""")
    conn.commit()

    # Seed one demo account per role the first time the DB is created,
    # so the app is usable out of the box. Remove/change these in production.
    existing = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if existing == 0:
        demo_password = generate_password_hash("1234")
        for role in ("Manufacturer", "Distributor", "Retailer"):
            c.execute(
                "INSERT INTO users(username,password,role) VALUES(?,?,?)",
                ("vidit", demo_password, role),
            )
        conn.commit()

    conn.close()
