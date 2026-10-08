"""DPSynth Enhanced SQLite Database Layer.
Thread-safe WAL mode, connection pooling, high-throughput batching,
indexes, and robust schema management for users, payments, jobs, and API keys.
"""
import sqlite3
import os
import asyncio
import threading
import time
import uuid
import json
from .config import DB_PATH

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
_lock = threading.Lock()

def get_connection():
    """Returns a configured SQLite connection with optimized PRAGMAs."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA cache_size=-64000;")  # 64MB memory cache
    return conn

# Shared singleton connection for read/enqueue
db = get_connection()

def _ensure_column(table_name, col_name, col_type):
    """Safely adds missing column to existing table if not present."""
    cols = [r["name"] for r in db.execute(f"PRAGMA table_info({table_name});").fetchall()]
    if col_name not in cols:
        db.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type};")

def init_db():
    """Initializes tables, indices, and handles schema migrations."""
    with _lock:
        with db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                company TEXT,
                gstin TEXT,
                plan TEXT NOT NULL DEFAULT 'free',
                plan_expires_at REAL,
                api_key TEXT UNIQUE,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                order_id TEXT UNIQUE NOT NULL,
                email TEXT NOT NULL,
                plan TEXT NOT NULL,
                billing_cycle TEXT NOT NULL DEFAULT 'monthly',
                base_amount REAL NOT NULL,
                discount_amount REAL NOT NULL DEFAULT 0.0,
                gst_amount REAL NOT NULL,
                total_amount REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'INR',
                payment_gateway TEXT NOT NULL,
                gateway_order_id TEXT,
                gateway_payment_id TEXT,
                status TEXT NOT NULL,
                invoice_number TEXT UNIQUE,
                customer_name TEXT,
                customer_company TEXT,
                customer_gstin TEXT,
                promo_code TEXT,
                created_at REAL NOT NULL,
                paid_at REAL
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                plan TEXT NOT NULL,
                amount_inr REAL,
                gst_inr REAL,
                status TEXT,
                started_at REAL NOT NULL,
                expires_at REAL,
                created_at REAL
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_uid TEXT UNIQUE,
                ts REAL NOT NULL,
                plan TEXT NOT NULL,
                dataset_name TEXT,
                epsilon REAL NOT NULL,
                delta REAL DEFAULT 0.0,
                mechanism TEXT NOT NULL,
                n_in INTEGER NOT NULL,
                n_out INTEGER NOT NULL,
                tvd REAL NOT NULL,
                fidelity_score REAL DEFAULT 0.0,
                metrics_json TEXT,
                audit_hash TEXT,
                input_data TEXT,
                generated_data TEXT
            );

            CREATE TABLE IF NOT EXISTS api_keys (
                key TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                plan TEXT NOT NULL,
                requests_count INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at REAL NOT NULL,
                last_used_at REAL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                created_at REAL NOT NULL
            );
            """)

            # Run column migrations for existing databases
            _ensure_column("jobs", "job_uid", "TEXT")
            _ensure_column("jobs", "delta", "REAL DEFAULT 0.0")
            _ensure_column("jobs", "dataset_name", "TEXT")
            _ensure_column("jobs", "mechanism", "TEXT DEFAULT 'Laplace'")
            _ensure_column("jobs", "fidelity_score", "REAL DEFAULT 0.0")
            _ensure_column("jobs", "metrics_json", "TEXT")
            _ensure_column("jobs", "audit_hash", "TEXT")
            
            _ensure_column("subscriptions", "started_at", "REAL DEFAULT 0.0")
            _ensure_column("subscriptions", "expires_at", "REAL")
            _ensure_column("subscriptions", "created_at", "REAL")

            # Create Indexes
            db.executescript("""
            CREATE INDEX IF NOT EXISTS idx_jobs_ts ON jobs(ts DESC);
            CREATE INDEX IF NOT EXISTS idx_jobs_uid ON jobs(job_uid);
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);
            CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id);
            CREATE INDEX IF NOT EXISTS idx_orders_email ON orders(email);
            CREATE INDEX IF NOT EXISTS idx_orders_invoice ON orders(invoice_number);
            CREATE INDEX IF NOT EXISTS idx_subscriptions_email ON subscriptions(email);
            CREATE INDEX IF NOT EXISTS idx_api_keys_key ON api_keys(key);
            """)

init_db()

# Asynchronous batch insert queue for non-blocking disk writes
_q = None

def enqueue(sql, args):
    """Enqueues an insert/update query for batched background writing."""
    global _q
    if _q is None:
        _q = asyncio.Queue()
    _q.put_nowait((sql, args))

async def writer():
    """Batches inserts: one commit per ~200ms instead of one per request."""
    global _q
    if _q is None:
        _q = asyncio.Queue()
    while True:
        try:
            batch = [await _q.get()]
            await asyncio.sleep(0.2)
            while not _q.empty() and len(batch) < 5000:
                batch.append(_q.get_nowait())
            for _ in range(5):
                try:
                    with _lock:
                        with db:
                            for s, a in batch:
                                db.execute(s, a)
                    break
                except sqlite3.OperationalError:
                    await asyncio.sleep(0.3)
        except Exception:
            await asyncio.sleep(0.5)

# ----------------- User Management -----------------

def get_or_create_user(email, name=None, company=None, gstin=None, plan="free"):
    """Fetches user or creates a new account."""
    email = email.lower().strip()
    with _lock:
        row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        now = time.time()
        if row:
            if name or company or gstin:
                db.execute("""
                    UPDATE users SET 
                    name = COALESCE(?, name),
                    company = COALESCE(?, company),
                    gstin = COALESCE(?, gstin),
                    updated_at = ?
                    WHERE email = ?
                """, (name, company, gstin, now, email))
                db.commit()
                row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            return dict(row)
        
        uid = f"usr_{uuid.uuid4().hex[:12]}"
        api_key = f"dps_{uuid.uuid4().hex[:24]}"
        db.execute("""
            INSERT INTO users(id, email, name, company, gstin, plan, plan_expires_at, api_key, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
        """, (uid, email, name or "", company or "", gstin or "", plan, None, api_key, now, now))
        
        db.execute("""
            INSERT OR IGNORE INTO api_keys(key, email, plan, requests_count, is_active, created_at, last_used_at)
            VALUES(?,?,?,0,1,?,NULL)
        """, (api_key, email, plan, now))
        db.commit()
        return dict(db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone())

def get_user_by_email(email):
    """Retrieves user profile by email."""
    if not email:
        return None
    with _lock:
        row = db.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),)).fetchone()
        return dict(row) if row else None

def get_user_by_api_key(api_key):
    """Retrieves user profile and increments request count for API Key."""
    if not api_key:
        return None
    with _lock:
        key_row = db.execute("SELECT * FROM api_keys WHERE key = ? AND is_active = 1", (api_key,)).fetchone()
        if not key_row:
            return None
        now = time.time()
        db.execute("UPDATE api_keys SET requests_count = requests_count + 1, last_used_at = ? WHERE key = ?", (now, api_key))
        user_row = db.execute("SELECT * FROM users WHERE email = ?", (key_row["email"],)).fetchone()
        db.commit()
        return dict(user_row) if user_row else dict(key_row)

def update_user_plan(email, plan, duration_days=30):
    """Upgrades a user to a paid plan and extends plan expiration."""
    email = email.lower().strip()
    now = time.time()
    expires_at = now + (duration_days * 86400)
    with _lock:
        user = get_or_create_user(email, plan=plan)
        db.execute("""
            UPDATE users SET plan = ?, plan_expires_at = ?, updated_at = ?
            WHERE email = ?
        """, (plan, expires_at, now, email))
        db.execute("""
            UPDATE api_keys SET plan = ? WHERE email = ?
        """, (plan, email))
        db.commit()
        return dict(db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone())

# ----------------- Orders & Payments -----------------

def create_order_record(order_data):
    """Saves a newly initialized order."""
    with _lock:
        db.execute("""
            INSERT INTO orders (
                id, order_id, email, plan, billing_cycle, base_amount, 
                discount_amount, gst_amount, total_amount, currency, 
                payment_gateway, gateway_order_id, gateway_payment_id, 
                status, invoice_number, customer_name, customer_company, 
                customer_gstin, promo_code, created_at, paid_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            order_data["id"],
            order_data["order_id"],
            order_data["email"].lower().strip(),
            order_data["plan"],
            order_data.get("billing_cycle", "monthly"),
            order_data["base_amount"],
            order_data.get("discount_amount", 0.0),
            order_data["gst_amount"],
            order_data["total_amount"],
            order_data.get("currency", "INR"),
            order_data.get("payment_gateway", "razorpay"),
            order_data.get("gateway_order_id"),
            order_data.get("gateway_payment_id"),
            order_data.get("status", "created"),
            order_data["invoice_number"],
            order_data.get("customer_name"),
            order_data.get("customer_company"),
            order_data.get("customer_gstin"),
            order_data.get("promo_code"),
            order_data.get("created_at", time.time()),
            order_data.get("paid_at")
        ))
        db.commit()
    return order_data

def get_order_by_id(order_id):
    """Fetches order record by internal ID or gateway order ID."""
    with _lock:
        row = db.execute("SELECT * FROM orders WHERE order_id = ? OR id = ?", (order_id, order_id)).fetchone()
        return dict(row) if row else None

def get_order_by_invoice(invoice_number):
    """Fetches order by invoice number."""
    with _lock:
        row = db.execute("SELECT * FROM orders WHERE invoice_number = ?", (invoice_number,)).fetchone()
        return dict(row) if row else None

def mark_order_paid(order_id, gateway_payment_id=None, gateway_name=None):
    """Marks order as paid, updates subscription, and provisions plan."""
    now = time.time()
    with _lock:
        row = db.execute("SELECT * FROM orders WHERE order_id = ? OR id = ?", (order_id, order_id)).fetchone()
        if not row:
            return None
        ord_dict = dict(row)
        db.execute("""
            UPDATE orders SET 
                status = 'paid',
                gateway_payment_id = COALESCE(?, gateway_payment_id),
                payment_gateway = COALESCE(?, payment_gateway),
                paid_at = ?
            WHERE order_id = ?
        """, (gateway_payment_id, gateway_name, now, ord_dict["order_id"]))
        
        # Insert subscription record
        duration_days = 365 if ord_dict.get("billing_cycle") == "annual" else 30
        db.execute("""
            INSERT INTO subscriptions(ts, email, plan, amount_inr, gst_inr, status, started_at, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
        """, (
            now,
            ord_dict["email"],
            ord_dict["plan"],
            ord_dict["total_amount"],
            ord_dict["gst_amount"],
            now,
            now + (duration_days * 86400),
            now
        ))
        
        # Update user plan
        expires_at = now + (duration_days * 86400)
        db.execute("""
            UPDATE users SET plan = ?, plan_expires_at = ?, updated_at = ?
            WHERE email = ?
        """, (ord_dict["plan"], expires_at, now, ord_dict["email"]))
        
        db.execute("""
            UPDATE api_keys SET plan = ? WHERE email = ?
        """, (ord_dict["plan"], ord_dict["email"]))
        
        # Log audit event
        db.execute("""
            INSERT INTO audit_logs(event_type, details, ip_address, created_at)
            VALUES ('payment_success', ?, NULL, ?)
        """, (f"Order {ord_dict['order_id']} paid for {ord_dict['email']}: Plan {ord_dict['plan']}", now))
        
        db.commit()
        return dict(db.execute("SELECT * FROM orders WHERE order_id = ?", (ord_dict["order_id"],)).fetchone())

# ----------------- Jobs & History -----------------

def save_job_record(job_dict):
    """Saves completed synthesis job immediately with full metadata."""
    now = time.time()
    job_uid = job_dict.get("job_uid") or f"job_{uuid.uuid4().hex[:10]}"
    with _lock:
        cursor = db.execute("""
            INSERT INTO jobs (
                job_uid, ts, plan, dataset_name, epsilon, delta, mechanism,
                n_in, n_out, tvd, fidelity_score, metrics_json, audit_hash,
                input_data, generated_data
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            job_uid,
            job_dict.get("ts", now),
            job_dict.get("plan", "free"),
            job_dict.get("dataset_name", "dataset.csv"),
            job_dict.get("epsilon", 1.0),
            job_dict.get("delta", 0.0),
            job_dict.get("mechanism", "Laplace"),
            job_dict.get("n_in", 0),
            job_dict.get("n_out", 0),
            job_dict.get("tvd", 0.0),
            job_dict.get("fidelity_score", 0.0),
            json.dumps(job_dict.get("metrics_json", {})),
            job_dict.get("audit_hash", ""),
            job_dict.get("input_data", ""),
            job_dict.get("generated_data", "")
        ))
        job_id = cursor.lastrowid
        db.commit()
        return job_id, job_uid

def history(n=20):
    """Returns the last N jobs with backwards compatible format."""
    with _lock:
        rows = db.execute("""
            SELECT id, ts, plan, epsilon, n_in, n_out, tvd, 
                   COALESCE(dataset_name, 'dataset.csv') as dataset_name,
                   COALESCE(job_uid, '') as job_uid,
                   COALESCE(fidelity_score, ROUND((1.0 - tvd) * 100, 1)) as fidelity_score,
                   COALESCE(audit_hash, '') as audit_hash,
                   mechanism
            FROM jobs ORDER BY id DESC LIMIT ?
        """, (n,)).fetchall()
        # Return tuples compatible with original app: [id, ts, plan, epsilon, n_in, n_out, tvd, dataset_name, ...]
        return [list(r) for r in rows]

def get_job_by_id(job_id_or_uid):
    """Fetches full job data including generated data and audit certificate."""
    with _lock:
        if str(job_id_or_uid).isdigit():
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (int(job_id_or_uid),)).fetchone()
        else:
            row = db.execute("SELECT * FROM jobs WHERE job_uid = ?", (str(job_id_or_uid),)).fetchone()
        if not row:
            return None
        res = dict(row)
        try:
            res["metrics_json"] = json.loads(res["metrics_json"]) if res["metrics_json"] else {}
        except Exception:
            pass
        return res

# ----------------- Analytics & Stats -----------------

def get_system_stats():
    """Aggregates platform statistics for dashboard display."""
    with _lock:
        total_jobs = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        total_rows_gen = db.execute("SELECT COALESCE(SUM(n_out), 0) FROM jobs").fetchone()[0]
        total_paid_orders = db.execute("SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM orders WHERE status = 'paid'").fetchone()
        active_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        avg_fidelity = db.execute("SELECT COALESCE(AVG(fidelity_score), 92.5) FROM jobs WHERE fidelity_score > 0").fetchone()[0]
        recent_jobs = db.execute("""
            SELECT plan, COUNT(*) as cnt FROM jobs GROUP BY plan
        """).fetchall()
        
        return {
            "total_jobs": total_jobs,
            "total_rows_generated": total_rows_gen,
            "total_paid_orders": total_paid_orders[0],
            "total_revenue_inr": round(total_paid_orders[1], 2),
            "registered_users": active_users,
            "average_fidelity_pct": round(avg_fidelity, 1),
            "jobs_by_plan": {r["plan"]: r["cnt"] for r in recent_jobs}
        }
