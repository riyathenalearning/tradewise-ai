from flask import Flask, render_template
import yfinance as yf
import pandas as pd
import datetime

app = Flask(__name__)

# Beginner friendly small price stocks
stocks = [
"SUZLON.NS",
"YESBANK.NS",
"IRFC.NS",
"IDEA.NS",
"RVNL.NS",
"NHPC.NS",
"IRCON.NS",
"HUDCO.NS",
"JPPOWER.NS",
"NBCC.NS"
]


def calculate_rsi(data, period=14):
    delta = data["Close"].diff()

    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def scan_stock(symbol):

    try:

        df = yf.download(symbol, period="6mo", interval="1d")

        if df.empty:
            return None

        df["MA44"] = df["Close"].rolling(44).mean()

        df["RSI"] = calculate_rsi(df)

        df["AvgVolume"] = df["Volume"].rolling(20).mean()

        df["VolumeRatio"] = df["Volume"] / df["AvgVolume"]

        latest = df.iloc[-1]

        price = round(latest["Close"],2)
        rsi = round(latest["RSI"],2)
        ma44 = round(latest["MA44"],2)
        volume_ratio = round(latest["VolumeRatio"],2)

        signal = "WAIT"

        if price > ma44 and rsi < 60 and volume_ratio > 1.2:
            signal = "BUY"

        elif rsi > 70:
            signal = "SELL"

        return {
            "stock": symbol.replace(".NS",""),
            "price": price,
            "rsi": rsi,
            "ma44": ma44,
            "volume_ratio": volume_ratio,
            "signal": signal
        }

    except:
        return None


def is_market_open():

    now = datetime.datetime.now()

    if now.weekday() >= 5:
        return False

    market_open = now.replace(hour=9, minute=15)
    market_close = now.replace(hour=15, minute=30)

    if market_open <= now <= market_close:
        return True

    return False


@app.route("/")

def home():

    market_status = "OPEN" if is_market_open() else "CLOSED"

    results = []

    for stock in stocks:

        data = scan_stock(stock)

        if data:
            results.append(data)

    buy_stocks = [x for x in results if x["signal"] == "BUY"]

    if market_status == "CLOSED":
        message = "Market is currently closed. Data shown is based on last trading session."
    else:
        message = "Live scan of swing trade opportunities."

    return render_template(
        "index.html",
        stocks=results,
        buy_stocks=buy_stocks,
        market_status=market_status,
        message=message
    )


if __name__ == "__main__":
    app.run(debug=True)