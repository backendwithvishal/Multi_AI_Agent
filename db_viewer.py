"""Database Viewer & Inspection Tool for TripMate AI

Usage:
    python db_viewer.py                 # Summary of all tables and row counts
    python db_viewer.py users           # View rows in 'users' table
    python db_viewer.py trips           # View rows in 'trips' table
    python db_viewer.py itineraries     # View rows in 'itineraries' table
    python db_viewer.py bookings        # View rows in 'bookings' table
    python db_viewer.py checkpoints     # View LangGraph checkpoints
    python db_viewer.py runs            # View workflow runs
    python db_viewer.py --all           # View recent rows from all tables
"""

import os
import sys
from pathlib import Path
from typing import Any, List, Tuple

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    print("[ERROR] psycopg is not installed. Run: pip install psycopg[binary,pool]")
    sys.exit(1)


def get_db_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return "postgresql://postgres:postgres@localhost:5432/tripmate_db"
    return url


def get_connection():
    url = get_db_url()
    try:
        return psycopg.connect(url, connect_timeout=5, row_factory=dict_row)
    except Exception as exc:
        print(f"\n[FAIL] Could not connect to PostgreSQL: {exc}")
        print(f"       Target URL: {url.split('@')[-1] if '@' in url else url}")
        sys.exit(1)


def list_tables(conn) -> List[Tuple[str, int]]:
    """Returns a list of public tables and their row counts."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
              AND table_type = 'BASE TABLE'
            ORDER BY table_name;
            """
        )
        tables = [row["table_name"] for row in cur.fetchall()]

    counts = []
    with conn.cursor() as cur:
        for t in tables:
            try:
                cur.execute(f'SELECT COUNT(*) AS cnt FROM "{t}";')
                cnt = cur.fetchone()["cnt"]
                counts.append((t, cnt))
            except Exception:
                counts.append((t, 0))
    return counts


def format_table(headers: List[str], rows: List[List[Any]], max_col_width: int = 35) -> str:
    if not rows:
        return "(Table is empty - 0 rows)"

    str_rows = []
    for row in rows:
        formatted = []
        for cell in row:
            val = str(cell) if cell is not None else "NULL"
            val = val.replace("\n", " ").strip()
            if len(val) > max_col_width:
                val = val[: max_col_width - 3] + "..."
            formatted.append(val)
        str_rows.append(formatted)

    col_widths = [len(h) for h in headers]
    for row in str_rows:
        for i, val in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(val))

    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    sep_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
    data_lines = [" | ".join(row[i].ljust(col_widths[i]) if i < len(row) else "".ljust(col_widths[i]) for i in range(len(headers))) for row in str_rows]

    return f"{header_line}\n{sep_line}\n" + "\n".join(data_lines)


def view_table(conn, table_name: str, limit: int = 10):
    print("\n" + "=" * 80)
    print(f"Table: {table_name} (Showing latest {limit} rows)")
    print("=" * 80)

    with conn.cursor() as cur:
        # Check if table exists
        cur.execute(
            """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position;
            """,
            (table_name,),
        )
        cols = [r["column_name"] for r in cur.fetchall()]
        if not cols:
            print(f"[!] Table '{table_name}' does not exist in public schema.")
            return

        order_clause = ""
        if "created_at" in cols:
            order_clause = "ORDER BY created_at DESC"
        elif "id" in cols:
            order_clause = "ORDER BY id DESC"

        cur.execute(f'SELECT * FROM "{table_name}" {order_clause} LIMIT %s;', (limit,))
        records = cur.fetchall()

        if not records:
            print("  (0 rows found)")
            return

        rows = [[rec.get(c) for c in cols] for rec in records]
        print(format_table(cols, rows))
        print("=" * 80)


def show_summary(conn):
    url = get_db_url()
    host_display = url.split("@")[-1] if "@" in url else url
    print("=" * 80)
    print("TripMate AI - PostgreSQL Database Inspector")
    print(f"Target Database: {host_display}")
    print("=" * 80)

    tables = list_tables(conn)
    if not tables:
        print("\n[!] No tables found in public schema. Have migrations been applied?")
        print("    Run: python app.py  (auto-applies migrations on startup)")
        return

    print(f"\nFound {len(tables)} tables:\n")
    print(f"  {'#':<4} {'Table Name':<32} {'Row Count':<12}")
    print("  " + "-" * 50)
    for i, (name, cnt) in enumerate(tables, 1):
        status_indicator = f"{cnt} rows" if cnt > 0 else "0 rows (empty)"
        print(f"  {i:<4} {name:<32} {status_indicator:<12}")

    print("\n" + "-" * 80)
    print("Quick Commands to inspect table data:")
    print("  python db_viewer.py users        -> Inspect registered users")
    print("  python db_viewer.py trips        -> Inspect created travel projects")
    print("  python db_viewer.py itineraries  -> Inspect generated itineraries")
    print("  python db_viewer.py bookings     -> Inspect flight/hotel reservations")
    print("  python db_viewer.py checkpoints  -> Inspect LangGraph agent checkpoints")
    print("  python db_viewer.py --all        -> Inspect all tables at once")
    print("=" * 80)


def main():
    conn = get_connection()
    try:
        args = sys.argv[1:]
        if not args:
            show_summary(conn)
        elif args[0] == "--all":
            tables = list_tables(conn)
            for name, cnt in tables:
                if cnt > 0:
                    view_table(conn, name, limit=5)
        else:
            table_name = args[0].strip()
            # Aliases for convenience
            alias_map = {
                "user": "users",
                "trip": "trips",
                "itinerary": "itineraries",
                "booking": "bookings",
                "run": "workflow_runs",
                "runs": "workflow_runs",
                "watchlist": "watchlists",
                "alert": "alerts",
                "asset": "assets",
                "checkpoint": "checkpoints",
            }
            target = alias_map.get(table_name, table_name)
            view_table(conn, target, limit=15)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

