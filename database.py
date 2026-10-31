"""
Cynbit Smart Inquiry Hub — database layer
SQLite persistence for qualified leads. Swap for Postgres in production
(Render free tier uses an ephemeral disk; schema is identical).
"""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "leads.db")


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                company TEXT,
                industry TEXT,
                service TEXT,
                budget TEXT,
                timeline TEXT,
                message TEXT NOT NULL,
                score INTEGER NOT NULL,
                tier TEXT NOT NULL,
                next_step TEXT NOT NULL,
                summary_type TEXT NOT NULL,
                intelligence TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'New'
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(score DESC)
        """)


def insert_lead(payload: dict) -> int:
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO leads (created_at, name, email, company, industry,
                               service, budget, timeline, message,
                               score, tier, next_step, summary_type, intelligence)
            VALUES (:created_at, :name, :email, :company, :industry,
                    :service, :budget, :timeline, :message,
                    :score, :tier, :next_step, :summary_type, :intelligence)
            """,
            payload,
        )
        return cur.lastrowid


def all_leads():
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM leads ORDER BY created_at DESC, score DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def update_status(lead_id: int, status: str) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE leads SET status = ? WHERE id = ?", (status, lead_id)
        )
        return cur.rowcount == 1


def stats():
    with _conn() as conn:
        rows = {r["k"]: r["v"] for r in conn.execute(
            """
            SELECT 'total' AS k, COUNT(*) AS v FROM leads
            UNION SELECT 'hot', COUNT(*) FROM leads WHERE tier = 'Hot'
            UNION SELECT 'warm', COUNT(*) FROM leads WHERE tier = 'Warm'
            UNION SELECT 'exploring', COUNT(*) FROM leads WHERE tier = 'Exploring'
            UNION SELECT 'avg_score', COALESCE(ROUND(AVG(score)), 0) FROM leads
            UNION SELECT 'contacted', COUNT(*) FROM leads WHERE status != 'New'
            UNION SELECT 'new_count', COUNT(*) FROM leads WHERE status = 'New'
            UNION SELECT 'newsletter_missing', COUNT(*) FROM leads WHERE 1=0
            """
        ).fetchall()}
        return rows


if __name__ == "__main__":
    init_db()
    print("DB initialised at", DB_PATH)
