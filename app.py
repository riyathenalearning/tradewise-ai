from flask import Flask, render_template_string
import yfinance as yf
import pandas as pd
import ta
from datetime import datetime
import pytz

app = Flask(__name__)

# Beginner friendly + popular NSE stocks
stocks = [
"SBIN.NS","IRFC.NS","NHPC.NS","SUZLON.NS","TATAMOTORS.NS",
"YESBANK.NS","IDEA.NS","BHEL.NS","PFC.NS","HUDCO.NS",
"IOC.NS","ONGC.NS","BANKBARODA.NS","PNB.NS","IDFCFIRSTB.NS",
"ITC.NS","HDFCBANK.NS","INFY.NS","WIPRO.NS","TCS.NS"
]

# ---------------------------------------

def get_market_status():

    india = pytz.timezone("Asia/Kolkata")
    now = datetime.now(india)

    if now.weekday() >= 5:
        return "Market Closed (Weekend)"

    if now.hour < 9 or (now.hour == 9 and now.minute < 15):
        return "Market Closed (Before Open)"

    if now.hour > 15 or (now.hour == 15 and now.minute > 30):
        return "Market Closed (After Market)"

    return "Market Open"

# ---------------------------------------

def scan_stock(stock):

    try:

        df = yf.download(stock, period="3mo", interval="1d")

        if df.empty:
            return None

        df["Close"] = pd.to_numeric(df["Close"])
        df["Volume"] = pd.to_numeric(df["Volume"])

        df["MA44"] = df["Close"].ewm(span=44).mean()

        df["RSI"] = ta.momentum.RSIIndicator(df["Close"]).rsi()

        df["AvgVolume"] = df["Volume"].rolling(20).mean()

        df["VolumeRatio"] = df["Volume"] / df["AvgVolume"]

        latest = df.iloc[-1]

        price = float(latest["Close"])
        rsi = float(latest["RSI"])
        ma44 = float(latest["MA44"])
        volume_ratio = float(latest["VolumeRatio"])

        signal = "WAIT"

        if price > ma44 and rsi > 55 and volume_ratio > 1.2:
            signal = "BUY"

        return {
            "stock": stock.replace(".NS",""),
            "price": round(price,2),
            "rsi": round(rsi,2),
            "ma44": round(ma44,2),
            "volume": round(volume_ratio,2),
            "signal": signal
        }

    except:
        return None

# ---------------------------------------

@app.route("/")

def home():

    results = []

    for stock in stocks:

        data = scan_stock(stock)

        if data:
            results.append(data)

    market = get_market_status()

    html = """

    <html>

    <head>

    <title>TradeWise AI</title>

    <style>

    body{
    font-family: Arial;
    background:#0f172a;
    color:white;
    padding:40px;
    }

    h1{
    color:#38bdf8;
    }

    table{
    border-collapse:collapse;
    width:100%;
    margin-top:20px;
    }

    th,td{
    padding:12px;
    text-align:center;
    border-bottom:1px solid #334155;
    }

    th{
    background:#1e293b;
    }

    .buy{
    background:#16a34a;
    padding:6px 14px;
    border-radius:6px;
    }

    .wait{
    background:#ef4444;
    padding:6px 14px;
    border-radius:6px;
    }

    </style>

    </head>

    <body>

    <h1>📈 TradeWise AI Scanner</h1>

    <h3>Market Status : {{market}}</h3>

    <table>

    <tr>

    <th>Stock</th>
    <th>Price</th>
    <th>RSI</th>
    <th>44 EMA</th>
    <th>Volume Boost</th>
    <th>Signal</th>

    </tr>

    {% for r in results %}

    <tr>

    <td>{{r.stock}}</td>
    <td>{{r.price}}</td>
    <td>{{r.rsi}}</td>
    <td>{{r.ma44}}</td>
    <td>{{r.volume}}</td>

    <td>

    {% if r.signal=="BUY" %}

    <span class="buy">BUY</span>

    {% else %}

    <span class="wait">WAIT</span>

    {% endif %}

    </td>

    </tr>

    {% endfor %}

    </table>

    {% if results|length == 0 %}

    <p>No market data available right now.</p>

    {% endif %}

    </body>

    </html>

    """

    return render_template_string(html,results=results,market=market)

# ---------------------------------------

if __name__ == "__main__":

    app.run(debug=True)