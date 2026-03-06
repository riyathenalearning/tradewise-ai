from flask import Flask, render_template
import yfinance as yf
import pandas as pd
import ta
from datetime import datetime
import pytz

app = Flask(__name__)

# Beginner friendly stocks (cheap + liquid)
STOCK_LIST = [
    "ITC.NS",
    "IRFC.NS",
    "RVNL.NS",
    "NHPC.NS",
    "NBCC.NS",
    "SAIL.NS",
    "BANKBARODA.NS",
    "PNB.NS",
    "IDEA.NS",
    "SUZLON.NS"
]


def scan_stock(stock):

    try:

        df = yf.download(stock, period="3mo", interval="1d")

        if df.empty:
            return None

        df["RSI"] = ta.momentum.RSIIndicator(df["Close"].squeeze()).rsi()

        df["MA44"] = df["Close"].rolling(44).mean()

        df["AvgVolume"] = df["Volume"].rolling(20).mean()

        df["VolumeRatio"] = df["Volume"] / df["AvgVolume"]

        latest = df.iloc[-1]

        price = float(latest["Close"])
        rsi = float(latest["RSI"])
        ma44 = float(latest["MA44"])
        vol_ratio = float(latest["VolumeRatio"])

        signal = "WAIT"

        if rsi > 55 and price > ma44 and vol_ratio > 1.5:
            signal = "BUY"

        if rsi < 45 and price < ma44:
            signal = "SELL"

        return {
            "stock": stock.replace(".NS", ""),
            "price": round(price, 2),
            "rsi": round(rsi, 2),
            "ma44": round(ma44, 2),
            "volume_ratio": round(vol_ratio, 2),
            "signal": signal
        }

    except:
        return None


def check_market_status():

    india = pytz.timezone("Asia/Kolkata")
    now = datetime.now(india)

    hour = now.hour
    minute = now.minute
    weekday = now.weekday()

    market_open = False

    if weekday < 5:
        if (hour > 9 or (hour == 9 and minute >= 15)) and (hour < 15 or (hour == 15 and minute <= 30)):
            market_open = True

    if market_open:
        return "🟢 Market Open"
    else:
        return "🔴 Market Closed (showing last data)"


@app.route("/")
def home():

    stocks_data = []

    for stock in STOCK_LIST:

        data = scan_stock(stock)

        if data:
            stocks_data.append(data)

    market_status = check_market_status()

    return render_template(
        "index.html",
        stocks=stocks_data,
        market_status=market_status
    )


if __name__ == "__main__":
    app.run(debug=True)