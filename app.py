from flask import Flask, render_template, request, redirect
import yfinance as yf
import pandas as pd
import datetime

app = Flask(__name__)

capital = 5000

stocks = [
"IRFC.NS","RVNL.NS","SUZLON.NS","IDEA.NS","NHPC.NS",
"IOC.NS","PFC.NS","RECLTD.NS","SAIL.NS","BHEL.NS",
"YESBANK.NS","IDFCFIRSTB.NS","BANKINDIA.NS",
"CANBK.NS","UCOBANK.NS","HUDCO.NS","IREDA.NS",
"TATAMOTORS.NS","COALINDIA.NS","ONGC.NS"
]

active_intraday_trades = []
active_swing_trades = []


def calculate_rsi(series, period=14):

    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (100/(1+rs))

    return rsi


def calculate_vwap(df):

    pv = (df["Close"] * df["Volume"]).cumsum()
    vol = df["Volume"].cumsum()

    return pv / vol


def scan_intraday():

    trades = []

    for stock in stocks:

        try:

            df = yf.download(stock, period="2d", interval="5m", progress=False)

            if df.empty:
                continue

            df["RSI"] = calculate_rsi(df["Close"])
            df["VWAP"] = calculate_vwap(df)

            price = df["Close"].iloc[-1]
            rsi = df["RSI"].iloc[-1]
            vwap = df["VWAP"].iloc[-1]

            avg_volume = df["Volume"].tail(10).mean()
            current_volume = df["Volume"].iloc[-1]

            if price < 500 and price > vwap and rsi > 55 and current_volume > avg_volume:

                entry = round(price,2)
                stoploss = round(price*0.985,2)
                target = round(price*1.03,2)

                qty = int(capital/price)

                trades.append({
                    "stock":stock,
                    "entry":entry,
                    "stoploss":stoploss,
                    "target":target,
                    "qty":qty
                })

        except:
            continue

    return trades


def scan_swing():

    trades = []

    for stock in stocks:

        try:

            df = yf.download(stock, period="3mo", interval="1d", progress=False)

            if df.empty:
                continue

            df["RSI"] = calculate_rsi(df["Close"])

            price = df["Close"].iloc[-1]
            rsi = df["RSI"].iloc[-1]

            ma50 = df["Close"].rolling(50).mean().iloc[-1]

            if price > ma50 and rsi < 60 and price < 500:

                entry = round(price,2)
                stoploss = round(price*0.95,2)
                target = round(price*1.12,2)

                qty = int(capital/price)

                trades.append({
                    "stock":stock,
                    "entry":entry,
                    "stoploss":stoploss,
                    "target":target,
                    "qty":qty
                })

        except:
            continue

    return trades


@app.route("/")
def home():

    intraday = scan_intraday()
    swing = scan_swing()

    time = datetime.datetime.now().strftime("%H:%M:%S")

    return render_template(
        "index.html",
        intraday_trades=intraday,
        swing_trades=swing,
        time=time
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)