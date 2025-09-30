
import sqlite3

conn = sqlite3.connect("db.sqlite3")
cursor = conn.cursor()

# Show tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print(cursor.fetchall())

# Show counts
for tbl in ["areas", "locations", "meters"]:
    cursor.execute(f"SELECT COUNT(*) FROM {tbl}")
    print(tbl, cursor.fetchone()[0])

# Peek some rows
cursor.execute("SELECT * FROM areas LIMIT 5;")
print(cursor.fetchall())