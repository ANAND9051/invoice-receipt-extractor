"""
SQLite database storage for persisting extraction history.
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from extractor.schemas import ExtractedInvoiceReceipt

DB_PATH = "extractions_history.db"


def init_db(db_path: str = DB_PATH):
    """Initializes the SQLite database table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS extractions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            filename TEXT,
            document_type TEXT,
            vendor_name TEXT,
            invoice_number TEXT,
            issue_date TEXT,
            total_amount REAL,
            currency TEXT,
            quality_score INTEGER,
            json_data TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_extraction(
    filename: str,
    doc: ExtractedInvoiceReceipt,
    quality_score: int,
    db_path: str = DB_PATH
) -> int:
    """Saves an extraction record to the database."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    json_str = json.dumps(doc.model_dump(), ensure_ascii=False)

    cursor.execute("""
        INSERT INTO extractions (
            created_at, filename, document_type, vendor_name,
            invoice_number, issue_date, total_amount, currency,
            quality_score, json_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        now_iso,
        filename,
        doc.document_type,
        doc.vendor.name if doc.vendor else None,
        doc.invoice_number,
        doc.issue_date,
        doc.total_amount,
        doc.currency,
        quality_score,
        json_str
    ))
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id


def get_all_extractions(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Retrieves all past extractions ordered by date descending."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM extractions ORDER BY id DESC")
    rows = cursor.fetchall()
    results = [dict(row) for row in rows]
    conn.close()
    return results


def delete_extraction(record_id: int, db_path: str = DB_PATH):
    """Deletes an extraction by ID."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM extractions WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()


def clear_all_extractions(db_path: str = DB_PATH):
    """Clears all extraction records."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM extractions")
    conn.commit()
    conn.close()
