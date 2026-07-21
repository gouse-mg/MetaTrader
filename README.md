# MT5 Dashboard

A self-hosted dashboard for your MetaTrader 5 account: live candlestick chart,
account balance/equity, open positions, and buy/sell buttons — all backed by
your real MT5 account state (demo or live).

## How it works

```
Browser (dashboard)  <-->  Flask backend (app.py)  <-->  MetaTrader5 terminal
     login form              MetaTrader5 package         your demo account
     chart + buttons         (local IPC, not cloud)
```

Everything you do in the dashboard (buy, sell, close) is sent through the
official `MetaTrader5` Python package straight to your terminal, so it's the
same account — balance, equity, and open positions update identically in the
MT5 terminal itself.

## Requirements — read this first

- **Windows only.** The `MetaTrader5` Python package connects to a running
  MT5 terminal via local IPC. It does not work on macOS/Linux (unless you run
  MT5 under Wine, which is unofficial/unsupported).
- **MetaTrader 5 terminal installed** on the same machine, with your demo
  account already known to it (you don't have to be logged in ahead of time —
  the app logs in for you — but the terminal application itself must be
  installed).
- **Python 3.9+**
- Your account **login (number)**, **master/trader password** (not the
  read-only "investor" password — that can view but can't place trades), and
  **server name** (e.g. `MetaQuotes-Demo` or a broker-specific name like
  `ICMarketsSC-Demo`). Find these in the terminal under
  *File → Login to Trade Account*, or in the email your broker sent when you
  opened the demo account.

## Setup

1. Unzip this project.
2. Open a terminal (PowerShell/cmd) in the `backend` folder.
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Run the server:
   ```
   python app.py
   ```
5. Open your browser to:
   ```
   http://127.0.0.1:5000
   ```
6. Enter your login, password, and server, and click **Connect**.

You'll land on the dashboard: account balance/equity at the top, a
candlestick chart with symbol/timeframe selectors, a buy/sell panel, and a
table of open positions with a close button on each.

## What's included

```
mt5_dashboard/
├── backend/
│   ├── app.py            # Flask API wrapping the MetaTrader5 package
│   └── requirements.txt
├── frontend/
│   ├── index.html        # Login screen + dashboard layout
│   ├── style.css
│   └── app.js            # Polling, chart rendering, buy/sell/close logic
└── README.md
```

## API endpoints (for reference / extending)

| Method | Path            | Purpose                                  |
|--------|-----------------|-------------------------------------------|
| POST   | `/api/connect`    | Log in with login/password/server         |
| POST   | `/api/disconnect` | Log out, shuts down the MT5 connection    |
| GET    | `/api/account`    | Current balance/equity/margin/profit      |
| GET    | `/api/symbols`    | List of visible/tradable symbols          |
| GET    | `/api/candles`    | OHLC candles (`?symbol=&timeframe=&count=`)|
| GET    | `/api/tick`       | Live bid/ask (`?symbol=`)                 |
| GET    | `/api/positions`  | Currently open positions                  |
| POST   | `/api/order`      | Place a market buy/sell order              |
| POST   | `/api/close`      | Close a position by ticket                 |

## Notes and caveats

- This app is built for **local, single-user use** (you, on your own
  machine). There's no multi-user auth system — anyone who can reach
  `127.0.0.1:5000` on your machine can trade on your account, so don't expose
  this port to the network without adding real authentication first.
- Demo accounts sometimes have simplified/instant fills compared to live
  execution (spread, slippage) — good for testing the plumbing, not for
  judging a strategy's real-world performance.
- If order placement fails with an authorization-style error, double check
  you used the **trader/master password**, not the investor (read-only) one.
- `ORDER_FILLING_IOC` is used by default in `app.py` — some brokers require
  `ORDER_FILLING_FOK` or `ORDER_FILLING_RETURN` instead. If orders get
  rejected with a "filling mode" error, change `type_filling` in `app.py`
  accordingly.
- This is not financial advice, and nothing here manages risk for you — SL/TP
  fields are optional and blank by default.
