import sys, traceback
try:
    import app
    app.app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
except Exception:
    with open("server_error.log", "w") as f:
        traceback.print_exc(file=f)
    sys.exit(1)