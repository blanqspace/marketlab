import os, sqlite3, datetime
db = os.environ.get("IPC_DB","runtime/ctl.db")
con = sqlite3.connect(db); cur = con.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS commands(
  id TEXT PRIMARY KEY, source TEXT NOT NULL, cmd TEXT NOT NULL,
  args TEXT NOT NULL, status TEXT NOT NULL, result TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
cur.execute("CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status)")
cur.execute("""CREATE TABLE IF NOT EXISTS events(
  id TEXT PRIMARY KEY, level TEXT NOT NULL, msg TEXT NOT NULL,
  ctx TEXT, ts TEXT NOT NULL)""")
con.commit(); con.close()
print("OK schema:", db)

