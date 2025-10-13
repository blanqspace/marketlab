import os, sqlite3, time, json
from datetime import datetime, timezone
from marketlab.ipc import bus

DB = os.environ.get("IPC_DB", "runtime/ctl.db")


def iso():
    return datetime.now(timezone.utc).isoformat()


def main():
    # Init bus schema (compatible with repo)
    bus.bus_init()

    # Ping-Event über Bus API
    bus.emit("info", "diag.ping", db=DB)

    # Enqueue state.pause über Bus API
    cmd_id = bus.enqueue("state.pause", {}, source="cli", ttl_sec=60)

    print("DB =", DB)
    print("ENQUEUED =", cmd_id)

    # Warten bis Worker verarbeitet (max 5s)
    status = "NEW"
    result = None
    con = sqlite3.connect(DB)
    try:
        for _ in range(10):
            time.sleep(0.5)
            row = con.execute(
                "SELECT status FROM commands WHERE cmd_id=?", (cmd_id,)
            ).fetchone()
            if row:
                status = row[0]
                if status != "NEW":
                    break
    finally:
        con.close()

    print("STATUS =", status)
    if status == "NEW":
        print("HINWEIS: Kein Worker aktiv oder andere IPC_DB im Worker-Fenster.")
    else:
        con = sqlite3.connect(DB)
        try:
            ev = con.execute(
                "SELECT level, message, ts FROM events ORDER BY id DESC LIMIT 5"
            ).fetchall()
            print("EVENTS_TAIL =", ev)
        finally:
            con.close()


if __name__ == "__main__":
    main()
