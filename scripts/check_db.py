#!/usr/bin/env python3
"""Quick inspection/validation helper for a built Cantonese dictionary DB."""

import sqlite3
import sys

db = sys.argv[1] if len(sys.argv) > 1 else "dist/cantonese.db"

con = sqlite3.connect(db)

required_tables = {
    "dictionary_entries",
    "characters",
    "english_index",
    "database_metadata",
    "dictionary_words",
}

tables = {
    row[0]
    for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
}

missing = required_tables - tables
unexpected = tables - required_tables

if missing:
    raise SystemExit(f"Missing tables: {sorted(missing)}")

if unexpected:
    print(f"Unexpected tables: {sorted(unexpected)}")

print("Tables:")
for table in sorted(required_tables):
    n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table}: {n:,}")

print("\nDatabase metadata:")
for row in con.execute(
    "SELECT key, value FROM database_metadata ORDER BY key"
):
    print(f"  {row[0]}: {row[1]}")

print("\nTop frequency entries:")
for row in con.execute("""
    SELECT word, pronunciation, frequency, frequency_band
    FROM dictionary_entries
    ORDER BY frequency DESC, word
    LIMIT 20
"""):
    print(row)

print("\nSample English lookups:")
for q in ("horse", "highlight"):
    rows = con.execute("""
        SELECT english_word, cantonese_word, rank
        FROM english_index
        WHERE english_normalized = ?
        ORDER BY rank
        LIMIT 20
    """, (q,)).fetchall()
    print(q, rows)

print("\nTop character frequencies:")
for row in con.execute("""
    SELECT character, jyutping, frequency, gloss_pronunciation, gloss
    FROM characters
    ORDER BY frequency DESC, character
    LIMIT 20
"""):
    print(row)

# The downloaded dictionary DB must not contain Tatoeba data.
for forbidden in ("tatoeba_sentences", "tatoeba_translations"):
    if forbidden in tables:
        raise SystemExit(
            f"Forbidden legacy table found: {forbidden}"
        )

con.close()
