"""
Robust server launcher for Jharkhand Samadhan.

- Auto-initialises the DB and seeds demo users if missing (survives a wiped
  database or a fresh clone of the repo).
- Binds 0.0.0.0 so the site is reachable from any device on the same network
  (http://<this-computer's-LAN-IP>:5000) as well as localhost.
- Runs with the reloader off (killed earlier), writes crashes to
  server_error.log, and exits cleanly if the port is already in use so
  duplicate auto-start instances don't double-run.
- Displays both the local and LAN addresses at startup.
"""

import os
import socket
import sys
import traceback


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
HOST = "0.0.0.0"
PORT = 5000


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def port_in_use(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def main():
    if port_in_use("127.0.0.1", PORT):
        print(f"Port {PORT} already in use — an instance of the server is probably already running.")
        sys.exit(0)

    try:
        import app
    except Exception:
        with open("server_error.log", "w") as f:
            traceback.print_exc(file=f)
        print("Startup failed — see server_error.log")
        sys.exit(1)

    # Ensure schema + demo accounts exist even on a fresh clone / wiped DB.
    try:
        app.db.init_db()
        app.seed_demo_users()
    except Exception:
        with open("server_error.log", "w") as f:
            traceback.print_exc(file=f)

    ip = lan_ip()
    print("Jharkhand Samadhan server running.")
    print("  On this computer: http://127.0.0.1:%d" % PORT)
    if ip:
        print("  On other devices (same Wi-Fi/network): http://%s:%d" % (ip, PORT))

    try:
        app.app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
    except Exception:
        with open("server_error.log", "w") as f:
            traceback.print_exc(file=f)
        sys.exit(1)


if __name__ == "__main__":
    main()