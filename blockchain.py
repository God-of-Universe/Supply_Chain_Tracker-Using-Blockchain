import hashlib
import time
import sqlite3

from database import DB_NAME


class Block:
    def __init__(self, index, data, prev_hash, timestamp=None, hash_value=None):
        self.index = index
        self.timestamp = timestamp or time.time()
        self.data = data
        self.prev_hash = prev_hash
        self.hash = hash_value or self.calculate_hash()

    def calculate_hash(self):
        payload = f"{self.index}{self.timestamp}{self.data}{self.prev_hash}"
        return hashlib.sha256(payload.encode()).hexdigest()


class Blockchain:
    def __init__(self):
        self.chain = []
        self.load_chain()

    def create_genesis_block(self):
        return Block(0, {"info": "Genesis Block"}, "0")

    def load_chain(self):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS blocks(
            idx INTEGER,timestamp REAL,product_id TEXT,description TEXT,
            status TEXT,role TEXT,prev_hash TEXT,hash TEXT)""")
        rows = c.execute("SELECT * FROM blocks ORDER BY idx").fetchall()
        conn.close()

        if not rows:
            genesis = self.create_genesis_block()
            self.chain = [genesis]
            self.save_block(genesis)
        else:
            self.chain = []
            for r in rows:
                data = {"product_id": r[2], "description": r[3], "status": r[4], "by": r[5]}
                self.chain.append(Block(r[0], data, r[6], r[1], r[7]))

    def save_block(self, block):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute(
            "INSERT INTO blocks VALUES(?,?,?,?,?,?,?,?)",
            (
                block.index,
                block.timestamp,
                block.data.get("product_id"),
                block.data.get("description"),
                block.data.get("status"),
                block.data.get("by"),
                block.prev_hash,
                block.hash,
            ),
        )
        conn.commit()
        conn.close()

    def add_block(self, data):
        last = self.chain[-1]
        block = Block(len(self.chain), data, last.hash)
        self.chain.append(block)
        self.save_block(block)

    def get_product_history(self, pid):
        return [b for b in self.chain if b.data.get("product_id") == pid]

    def get_all_products(self):
        """One row per distinct product_id: latest status plus per-stage
        completion flags (manufactured / distributed / retailed), so callers
        can tell how far a product has moved through the supply chain."""
        grouped = {}
        for b in self.chain:
            pid = b.data.get("product_id")
            if not pid:
                continue
            grouped.setdefault(pid, []).append(b)

        products = {}
        for pid, blocks in grouped.items():
            blocks.sort(key=lambda b: b.index)
            first, last = blocks[0], blocks[-1]
            products[pid] = {
                "product_id": pid,
                "description": last.data.get("description") or first.data.get("description", ""),
                "status": last.data.get("status", ""),
                "created_at": first.timestamp,
                "updated_at": last.timestamp,
                "manufactured": any(b.data.get("by") == "Manufacturer" for b in blocks),
                "distributed": any(b.data.get("by") == "Distributor" for b in blocks),
                "retailed": any(
                    b.data.get("by") == "Retailer" and b.data.get("status") in ("Delivered", "Sold")
                    for b in blocks
                ),
            }
        return products

    def validate_chain(self):
        for i in range(1, len(self.chain)):
            cur = self.chain[i]
            prev = self.chain[i - 1]
            if cur.hash != cur.calculate_hash():
                return False
            if cur.prev_hash != prev.hash:
                return False
        return True

    def get_stats(self):
        # total should count distinct products, not every block/update on the chain.
        products = self.get_all_products()
        stats = {"total": len(products), "in_transit": 0, "delivered": 0, "sold": 0}
        for p in products.values():
            status = p["status"]
            if status == "In Transit":
                stats["in_transit"] += 1
            elif status == "Delivered":
                stats["delivered"] += 1
            elif status == "Sold":
                stats["sold"] += 1
        return stats
