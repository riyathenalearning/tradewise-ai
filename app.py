from flask import Flask, render_template, request, redirect, jsonify
import yfinance as yf
import pandas as pd
import datetime
import json
import os
import threading
import time
import pytz

app = Flask(__name__)

CAPITAL = 5000
DATA_FILE    = "trades.json"
HISTORY_FILE = "history.json"
IST = pytz.timezone("Asia/Kolkata")

# ── Expanded stock universe: Nifty 50 + Nifty Midcap ─────────────
STOCKS = [
    # Original watchlist
    "IRFC.NS","RVNL.NS","SUZLON.NS","IDEA.NS","NHPC.NS",
    "IOC.NS","PFC.NS","RECLTD.NS","SAIL.NS","BHEL.NS",
    "YESBANK.NS","IDFCFIRSTB.NS","BANKINDIA.NS",
    "CANBK.NS","UCOBANK.NS","HUDCO.NS","IREDA.NS",
    "TATAMOTORS.BO","COALINDIA.NS","ONGC.NS",      # .BO = BSE fallback for Tata Motors
    # Nifty 50 Large Caps
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS",
    "HINDUNILVR.NS","SBIN.NS","BAJFINANCE.NS","BHARTIARTL.NS","KOTAKBANK.NS",
    "ITC.NS","LT.NS","AXISBANK.NS","ASIANPAINT.NS","MARUTI.NS",
    "SUNPHARMA.NS","TITAN.NS","ULTRACEMCO.NS","WIPRO.NS","HCLTECH.NS",
    "POWERGRID.NS","NTPC.NS","M&M.NS","BAJAJFINSV.NS","JSWSTEEL.NS",
    "ADANIENT.NS","ADANIPORTS.NS","GRASIM.NS","TECHM.NS","INDUSINDBK.NS",
    "DRREDDY.NS","BPCL.NS","CIPLA.NS","EICHERMOT.NS","DIVISLAB.NS",
    "APOLLOHOSP.NS","TATACONSUM.NS","SBILIFE.NS","HDFCLIFE.NS",
    "BRITANNIA.NS","NESTLEIND.NS","HEROMOTOCO.NS","UPL.NS",
    # Nifty Midcap highlights
    "ABCAPITAL.NS","ASTRAL.NS","AUROPHARMA.NS","BALKRISIND.NS",
    "BANDHANBNK.NS","BHARATFORG.NS","CHOLAFIN.NS","COFORGE.NS",
    "CROMPTON.NS","DEEPAKNTR.NS","FEDERALBNK.NS",
    "GMRAIRPORT.NS","GODREJPROP.NS","HINDPETRO.NS","INDUSTOWER.NS", # GMRINFRA → GMRAIRPORT
    "JUBLFOOD.NS","LICHSGFIN.NS","LUPIN.NS","MANAPPURAM.NS",
    "MFSL.NS","MOTHERSON.NS","MPHASIS.NS","NATIONALUM.NS",
    "NMDC.NS","PERSISTENT.NS","PETRONET.NS",
    "PIIND.NS","POLYCAB.NS","SUNTV.NS",
    "TATACOMM.NS","TVSMOTOR.NS","VOLTAS.NS",
]

# ── In-memory cache ───────────────────────────────────────────────
_cache = {
    "intraday":  [],
    "swing":     [],
    "last_scan": None,
    "lock":      threading.Lock()
}

# ── Subscription store ────────────────────────────────────────────
SUBS_FILE = "subscriptions.json"

def load_subscriptions():
    if os.path.exists(SUBS_FILE):
        with open(SUBS_FILE) as f:
            return json.load(f)
    return []

def save_subscriptions(subs):
    with open(SUBS_FILE, "w") as f:
        json.dump(subs, f, indent=2)

# ── Trade & history storage ───────────────────────────────────────
def load_trades():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"intraday": [], "swing": []}

def save_trades(trades):
    with open(DATA_FILE, "w") as f:
        json.dump(trades, f, indent=2)

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return []

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

def append_history(entry):
    history = load_history()
    history.insert(0, entry)
    save_history(history)

# ── Market hours ──────────────────────────────────────────────────
def is_market_open():
    now = datetime.datetime.now(IST)
    if now.weekday() >= 5:
        return False
    o = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    c = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return o <= now <= c

def market_status():
    now = datetime.datetime.now(IST)
    if now.weekday() >= 5:
        return "Closed (Weekend)"
    o = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    c = now.replace(hour=15, minute=30, second=0, microsecond=0)
    if now < o: return "Pre-market (Opens at 09:15 IST)"
    if now > c: return "Closed (Closed at 15:30 IST)"
    return "Open ✅"

# ── Indicators ────────────────────────────────────────────────────
def calculate_rsi(series, period=14):
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))

def calculate_vwap(df):
    pv  = (df["Close"] * df["Volume"]).cumsum()
    return pv / df["Volume"].cumsum()

def calculate_macd(series, fast=12, slow=26, signal=9):
    ema_fast    = series.ewm(span=fast,   adjust=False).mean()
    ema_slow    = series.ewm(span=slow,   adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line, macd_line - signal_line

def trigger_price(price, pct=0.002):
    """Trigger = current price (entry). Small buffer shown as context."""
    return round(price, 2)

# ── Scanners ──────────────────────────────────────────────────────
def scan_intraday():
    trades = []
    for stock in STOCKS:
        try:
            df = yf.download(stock, period="2d", interval="5m", progress=False)
            if df.empty or len(df) < 20:
                continue
            close = df["Close"].squeeze()
            df["RSI"]  = calculate_rsi(close)
            df["VWAP"] = calculate_vwap(df)
            macd_line, signal_line, histogram = calculate_macd(close)

            price        = safe_float(close.iloc[-1])
            rsi          = safe_float(df["RSI"].iloc[-1])
            vwap         = safe_float(df["VWAP"].iloc[-1])
            macd_val     = safe_float(macd_line.iloc[-1])
            signal_val   = safe_float(signal_line.iloc[-1])
            avg_vol      = safe_float(df["Volume"].squeeze().tail(10).mean())
            cur_vol      = safe_float(df["Volume"].squeeze().iloc[-1])

            if any(v is None for v in [price, rsi, vwap, macd_val, signal_val, avg_vol, cur_vol]):
                continue

            macd_bullish = (macd_val > signal_val and
                            safe_float(histogram.iloc[-1]) > safe_float(histogram.iloc[-2]))

            if (price < 500 and price > vwap
                    and 55 < rsi < 75
                    and cur_vol > avg_vol * 1.2
                    and macd_bullish):

                trades.append({
                    "stock":       stock.replace(".NS", "").replace(".BO", ""),
                    "full_ticker": stock,
                    "trigger":     trigger_price(price),
                    "entry":       round(price, 2),
                    "stoploss":    round(price * 0.985, 2),
                    "target":      round(price * 1.03, 2),
                    "qty":         int(CAPITAL / price),
                    "rsi":         round(rsi, 1),
                    "point_gain":  round(price * 0.03, 2),
                    "signal":      "RSI+VWAP+MACD",
                })
        except Exception:
            continue
    return trades

def scan_swing():
    trades = []
    for stock in STOCKS:
        try:
            df = yf.download(stock, period="3mo", interval="1d", progress=False)
            if df.empty or len(df) < 50:
                continue
            close = df["Close"].squeeze()
            df["RSI"] = calculate_rsi(close)
            macd_line, signal_line, _ = calculate_macd(close)

            price      = safe_float(close.iloc[-1])
            rsi        = safe_float(df["RSI"].iloc[-1])
            ma50       = safe_float(close.rolling(50).mean().iloc[-1])
            macd_val   = safe_float(macd_line.iloc[-1])
            signal_val = safe_float(signal_line.iloc[-1])
            ma20_now   = safe_float(close.rolling(20).mean().iloc[-1])
            ma20_prev  = safe_float(close.rolling(20).mean().iloc[-5])

            if any(v is None for v in [price, rsi, ma50, macd_val, signal_val, ma20_now, ma20_prev]):
                continue

            if (price < 500 and price > ma50
                    and 45 < rsi < 65
                    and ma20_now > ma20_prev
                    and macd_val > signal_val):

                trades.append({
                    "stock":       stock.replace(".NS", "").replace(".BO", ""),
                    "full_ticker": stock,
                    "trigger":     trigger_price(price),
                    "entry":       round(price, 2),
                    "stoploss":    round(price * 0.95, 2),
                    "target":      round(price * 1.12, 2),
                    "qty":         int(CAPITAL / price),
                    "rsi":         round(rsi, 1),
                    "point_gain":  round(price * 0.12, 2),
                    "signal":      "MA50+MACD+RSI",
                })
        except Exception:
            continue
    return trades

# ── Background scanner ────────────────────────────────────────────
def background_scanner():
    while True:
        if is_market_open():
            intraday = scan_intraday()
            swing    = scan_swing()
            with _cache["lock"]:
                _cache["intraday"]  = intraday
                _cache["swing"]     = swing
                _cache["last_scan"] = datetime.datetime.now(IST).strftime("%H:%M:%S IST")
            time.sleep(300)
        else:
            if _cache["last_scan"] is None:
                intraday = scan_intraday()
                swing    = scan_swing()
                with _cache["lock"]:
                    _cache["intraday"]  = intraday
                    _cache["swing"]     = swing
                    _cache["last_scan"] = (datetime.datetime.now(IST)
                                           .strftime("%H:%M:%S IST") + " (last close)")
            time.sleep(600)

# ── Reliable price fetcher ────────────────────────────────────────
def safe_float(val):
    """Safely extract a float from a scalar, Series, or 1-element Series."""
    try:
        if hasattr(val, "iloc"):
            return float(val.iloc[0])
        return float(val)
    except Exception:
        return None

def get_current_price(ticker):
    """
    Fetch the most accurate available price for an NSE stock.
    Strategy (in order of reliability):
      1. yf.Ticker.fast_info  → fastest, works market hours & after close
      2. yf.Ticker.history 1d → daily OHLCV, always has correct close
      3. yf.download 5d/1d    → last-resort fallback
    Returns None only if all methods fail.
    """
    # ── Method 1: fast_info (most reliable, single API call) ─────
    try:
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.fast_info

        # During market hours: last_price is live
        # After market close: last_price = closing price (correct)
        price = safe_float(info.last_price)
        if price and price > 0:
            return round(price, 2)
    except Exception:
        pass

    # ── Method 2: history() daily bar ────────────────────────────
    try:
        ticker_obj = yf.Ticker(ticker)
        hist = ticker_obj.history(period="2d", interval="1d")
        if not hist.empty:
            price = safe_float(hist["Close"].iloc[-1])
            if price and price > 0:
                return round(price, 2)
    except Exception:
        pass

    # ── Method 3: download fallback ───────────────────────────────
    try:
        df = yf.download(ticker, period="5d", interval="1d", progress=False)
        if not df.empty:
            close_col = df["Close"].squeeze()
            price = safe_float(close_col.iloc[-1])
            if price and price > 0:
                return round(price, 2)
    except Exception:
        pass

    return None

def enrich_active_trades(trades_list):
    enriched = []
    for t in trades_list:
        t = dict(t)
        ticker  = t.get("full_ticker", t["stock"] + ".NS")
        current = get_current_price(ticker)

        if current and current > 0:
            t["current"] = current
            pnl = round((current - t["entry"]) * t.get("qty", 1), 2)
            t["pnl"] = pnl
            if current >= t["target"]:
                t["status"] = "🎯 Target Hit"
            elif current <= t["stoploss"]:
                t["status"] = "🛑 SL Hit"
            else:
                pct = round(((current - t["entry"]) / t["entry"]) * 100, 2)
                t["status"] = f"{'▲' if pct >= 0 else '▼'} {pct}%"
        else:
            t["current"] = "—"
            t["pnl"]     = "—"
            t["status"]  = "Fetching…"
        enriched.append(t)
    return enriched

# ── Routes ────────────────────────────────────────────────────────
@app.route("/")
def home():
    with _cache["lock"]:
        intraday  = list(_cache["intraday"])
        swing     = list(_cache["swing"])
        last_scan = _cache["last_scan"] or "Scanning…"

    trades          = load_trades()
    active_intraday = enrich_active_trades(trades["intraday"])
    active_swing    = enrich_active_trades(trades["swing"])
    history         = load_history()

    # Summary stats for history
    total_trades = len(history)
    total_pnl    = sum(h["pnl"] for h in history if isinstance(h.get("pnl"), (int, float)))
    wins         = sum(1 for h in history if isinstance(h.get("pnl"), (int, float)) and h["pnl"] > 0)
    win_rate     = round((wins / total_trades * 100), 1) if total_trades else 0

    return render_template(
        "index.html",
        intraday_trades=intraday,
        swing_trades=swing,
        active_intraday_trades=active_intraday,
        active_swing_trades=active_swing,
        history=history,
        total_pnl=round(total_pnl, 2),
        win_rate=win_rate,
        total_trades=total_trades,
        last_scan=last_scan,
        market_status=market_status(),
        capital=CAPITAL,
    )

@app.route("/buy_intraday", methods=["POST"])
def buy_intraday():
    trades = load_trades()
    now    = datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    trade  = {
        "stock":       request.form["stock"],
        "full_ticker": request.form["stock"] + ".NS",
        "trigger":     float(request.form.get("trigger", request.form["entry"])),
        "entry":       float(request.form["entry"]),
        "stoploss":    float(request.form["stoploss"]),
        "target":      float(request.form["target"]),
        "qty":         int(request.form.get("qty", 1)),
        "type":        "Intraday",
        "bought_at":   now,
    }
    trades["intraday"].append(trade)
    save_trades(trades)
    return redirect("/")

@app.route("/buy_swing", methods=["POST"])
def buy_swing():
    trades = load_trades()
    now    = datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    trade  = {
        "stock":       request.form["stock"],
        "full_ticker": request.form["stock"] + ".NS",
        "trigger":     float(request.form.get("trigger", request.form["entry"])),
        "entry":       float(request.form["entry"]),
        "stoploss":    float(request.form["stoploss"]),
        "target":      float(request.form["target"]),
        "qty":         int(request.form.get("qty", 1)),
        "type":        "Swing",
        "bought_at":   now,
    }
    trades["swing"].append(trade)
    save_trades(trades)
    return redirect("/")

@app.route("/close_trade", methods=["POST"])
def close_trade():
    trade_type = request.form["type"]
    index      = int(request.form["index"])
    exit_price = request.form.get("exit_price", "").strip()
    trades     = load_trades()

    if 0 <= index < len(trades[trade_type]):
        closed = dict(trades[trade_type][index])
        try:
            ep = float(exit_price)
        except (ValueError, TypeError):
            ep = get_current_price(closed.get("full_ticker", closed["stock"] + ".NS"))
            ep = ep or closed["entry"]

        qty = closed.get("qty", 1)
        pnl = round((ep - closed["entry"]) * qty, 2)
        now = datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        append_history({
            "stock":     closed["stock"],
            "type":      closed.get("type", trade_type.capitalize()),
            "entry":     closed["entry"],
            "exit":      round(ep, 2),
            "stoploss":  closed.get("stoploss", "—"),
            "target":    closed.get("target", "—"),
            "qty":       qty,
            "pnl":       pnl,
            "bought_at": closed.get("bought_at", "—"),
            "sold_at":   now,
            "outcome":   "✅ Profit" if pnl > 0 else ("🛑 Loss" if pnl < 0 else "➖ Breakeven"),
        })
        trades[trade_type].pop(index)
        save_trades(trades)
    return redirect("/")

@app.route("/clear_history", methods=["POST"])
def clear_history():
    save_history([])
    return redirect("/")

@app.route("/api/subscribe", methods=["POST"])
def subscribe():
    sub  = request.get_json()
    subs = load_subscriptions()
    endpoints = {s.get("endpoint") for s in subs}
    if sub.get("endpoint") not in endpoints:
        subs.append(sub)
        save_subscriptions(subs)
    return jsonify({"status": "ok"})

@app.route("/api/scan")
def api_scan():
    with _cache["lock"]:
        return jsonify({
            "intraday":  _cache["intraday"],
            "swing":     _cache["swing"],
            "last_scan": _cache["last_scan"],
            "market":    market_status(),
        })

@app.route("/api/history")
def api_history():
    return jsonify(load_history())

# ── Serve PWA static files (fixes 404 on manifest & sw) ──────────
@app.route("/sw.js")
def serve_sw():
    from flask import send_from_directory
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "sw.js",
                               mimetype="application/javascript")

@app.route("/manifest.json")
def serve_manifest():
    from flask import send_from_directory
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "manifest.json",
                               mimetype="application/json")

scanner_thread = threading.Thread(target=background_scanner, daemon=True)
scanner_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)