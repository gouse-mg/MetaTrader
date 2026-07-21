"""
MT5 Dashboard Backend
----------------------
A small Flask server that wraps the official `MetaTrader5` Python package
and exposes it as a simple JSON API for the web dashboard.

IMPORTANT: This must run on the SAME Windows machine as your MetaTrader 5
terminal, because the MetaTrader5 package talks to the terminal via local
IPC - it is not a remote/cloud API. See README.md for setup steps.

Run with:
    python app.py
Then open http://127.0.0.1:5000 in your browser.
"""

import threading
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None  # Allows the file to at least be imported/inspected on non-Windows machines.

app = Flask(__name__, static_folder="../frontend", static_url_path="")

# A lock because the MetaTrader5 package is not designed for concurrent calls
# from multiple threads, and Flask's dev server can handle requests in parallel.
mt5_lock = threading.Lock()

# Simple in-memory connection state (single local user, no multi-tenant auth needed).
state = {
    "connected": False,
    "login": None,
    "server": None,
}

TIMEFRAME_MAP = {}


def _build_timeframe_map():
    """Populate the timeframe map once MetaTrader5 is importable."""
    if mt5 is None:
        return
    TIMEFRAME_MAP.update({
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    })


_build_timeframe_map()


def require_mt5():
    if mt5 is None:
        return jsonify({
            "error": "MetaTrader5 package is not installed / not usable on this OS. "
                     "This backend must run on Windows with MT5 terminal installed."
        }), 500
    return None


def require_connected():
    if not state["connected"]:
        return jsonify({"error": "Not connected. Please log in first."}), 401
    return None


def account_to_dict(info):
    if info is None:
        return None
    d = info._asdict()
    return d


def position_to_dict(pos):
    d = pos._asdict()
    d["type_str"] = "buy" if d["type"] == mt5.POSITION_TYPE_BUY else "sell"
    return d


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.route("/api/connect", methods=["POST"])
def connect():
    err = require_mt5()
    if err:
        return err

    data = request.get_json(force=True) or {}
    login = data.get("login")
    password = data.get("password")
    server = data.get("server")

    if not login or not password or not server:
        return jsonify({"error": "login, password and server are all required"}), 400

    try:
        login = int(login)
    except ValueError:
        return jsonify({"error": "login must be numeric (your MT5 account number)"}), 400

    with mt5_lock:
        if not mt5.initialize():
            return jsonify({"error": f"MT5 initialize() failed: {mt5.last_error()}"}), 500

        ok = mt5.login(login=login, password=password, server=server)
        if not ok:
            code, desc = mt5.last_error()
            mt5.shutdown()
            return jsonify({"error": f"Login failed ({code}): {desc}"}), 401

        info = mt5.account_info()

    state["connected"] = True
    state["login"] = login
    state["server"] = server

    return jsonify({"connected": True, "account": account_to_dict(info)})


@app.route("/api/disconnect", methods=["POST"])
def disconnect():
    if mt5 is not None:
        with mt5_lock:
            mt5.shutdown()
    state["connected"] = False
    state["login"] = None
    state["server"] = None
    return jsonify({"connected": False})


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------

@app.route("/api/account", methods=["GET"])
def account():
    err = require_mt5() or require_connected()
    if err:
        return err
    with mt5_lock:
        info = mt5.account_info()
    if info is None:
        return jsonify({"error": f"Could not fetch account info: {mt5.last_error()}"}), 500
    return jsonify(account_to_dict(info))


# ---------------------------------------------------------------------------
# Symbols / candles / ticks
# ---------------------------------------------------------------------------

@app.route("/api/symbols", methods=["GET"])
def symbols():
    err = require_mt5() or require_connected()
    if err:
        return err
    with mt5_lock:
        syms = mt5.symbols_get()
    if syms is None:
        return jsonify({"error": f"Could not fetch symbols: {mt5.last_error()}"}), 500
    # Only send names to keep the payload small; frontend can request more if needed.
    names = sorted({s.name for s in syms if s.visible})
    return jsonify(names[:500])


@app.route("/api/candles", methods=["GET"])
def candles():
    err = require_mt5() or require_connected()
    if err:
        return err

    symbol = request.args.get("symbol", "EURUSD")
    timeframe = request.args.get("timeframe", "M15")
    count = int(request.args.get("count", 200))

    tf = TIMEFRAME_MAP.get(timeframe)
    if tf is None:
        return jsonify({"error": f"Unknown timeframe '{timeframe}'"}), 400

    with mt5_lock:
        mt5.symbol_select(symbol, True)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)

    if rates is None:
        return jsonify({"error": f"Could not fetch candles for {symbol}: {mt5.last_error()}"}), 500

    result = [
        {
            "time": int(r["time"]),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": int(r["tick_volume"]),
        }
        for r in rates
    ]
    return jsonify(result)


@app.route("/api/tick", methods=["GET"])
def tick():
    err = require_mt5() or require_connected()
    if err:
        return err

    symbol = request.args.get("symbol", "EURUSD")
    with mt5_lock:
        mt5.symbol_select(symbol, True)
        t = mt5.symbol_info_tick(symbol)

    if t is None:
        return jsonify({"error": f"Could not fetch tick for {symbol}: {mt5.last_error()}"}), 500

    return jsonify({
        "symbol": symbol,
        "bid": t.bid,
        "ask": t.ask,
        "time": int(t.time),
    })


# ---------------------------------------------------------------------------
# Positions / trading
# ---------------------------------------------------------------------------

@app.route("/api/positions", methods=["GET"])
def positions():
    err = require_mt5() or require_connected()
    if err:
        return err
    with mt5_lock:
        pos = mt5.positions_get()
    if pos is None:
        pos = []
    return jsonify([position_to_dict(p) for p in pos])


@app.route("/api/order", methods=["POST"])
def order():
    err = require_mt5() or require_connected()
    if err:
        return err

    data = request.get_json(force=True) or {}
    symbol = data.get("symbol")
    side = data.get("side")  # "buy" or "sell"
    volume = data.get("volume")
    sl = data.get("sl")  # optional stop loss price
    tp = data.get("tp")  # optional take profit price

    if not symbol or side not in ("buy", "sell") or not volume:
        return jsonify({"error": "symbol, side ('buy'/'sell') and volume are required"}), 400

    try:
        volume = float(volume)
    except ValueError:
        return jsonify({"error": "volume must be a number"}), 400

    with mt5_lock:
        mt5.symbol_select(symbol, True)
        t = mt5.symbol_info_tick(symbol)
        if t is None:
            return jsonify({"error": f"Could not fetch price for {symbol}"}), 500

        order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
        price = t.ask if side == "buy" else t.bid

        request_dict = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "deviation": 20,
            "magic": 234000,
            "comment": "mt5-dashboard",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        if sl:
            request_dict["sl"] = float(sl)
        if tp:
            request_dict["tp"] = float(tp)

        result = mt5.order_send(request_dict)

    if result is None:
        return jsonify({"error": f"order_send failed: {mt5.last_error()}"}), 500

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return jsonify({
            "error": f"Order rejected, retcode={result.retcode}",
            "comment": result.comment,
        }), 400

    return jsonify({
        "success": True,
        "order": result.order,
        "price": result.price,
        "volume": result.volume,
    })


@app.route("/api/close", methods=["POST"])
def close_position():
    err = require_mt5() or require_connected()
    if err:
        return err

    data = request.get_json(force=True) or {}
    ticket = data.get("ticket")
    if not ticket:
        return jsonify({"error": "ticket is required"}), 400

    with mt5_lock:
        positions = mt5.positions_get(ticket=int(ticket))
        if not positions:
            return jsonify({"error": f"Position {ticket} not found"}), 404

        pos = positions[0]
        symbol = pos.symbol
        volume = pos.volume
        mt5.symbol_select(symbol, True)
        t = mt5.symbol_info_tick(symbol)

        # Closing a position means sending the opposite order type.
        if pos.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = t.bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = t.ask

        request_dict = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "position": int(ticket),
            "price": price,
            "deviation": 20,
            "magic": 234000,
            "comment": "mt5-dashboard-close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request_dict)

    if result is None:
        return jsonify({"error": f"order_send failed: {mt5.last_error()}"}), 500

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return jsonify({
            "error": f"Close rejected, retcode={result.retcode}",
            "comment": result.comment,
        }), 400

    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
