#!/usr/bin/env python3
"""
跨交易所搬砖套利机器人
监控 Gate.io vs Binance 现货价差，自动套利
全自动运行，GitHub Actions 免费托管
"""

import os
import json
import time
import hmac
import hashlib
import requests
from datetime import datetime

# ============ 配置 ============
GATE_API_KEY = os.environ.get("GATE_API_KEY", "")
GATE_API_SECRET = os.environ.get("GATE_API_SECRET", "")

# 监控的交易对 (两边交易所格式不同，需要映射)
PAIRS = [
    {"symbol": "BTC", "gate_pair": "BTC_USDT", "binance_symbol": "BTCUSDT"},
    {"symbol": "ETH", "gate_pair": "ETH_USDT", "binance_symbol": "ETHUSDT"},
    {"symbol": "SOL", "gate_pair": "SOL_USDT", "binance_symbol": "SOLUSDT"},
]

MIN_PROFIT_PERCENT = float(os.environ.get("MIN_PROFIT", "0.3"))  # 最低利润0.3%
TRADE_USDT = float(os.environ.get("TRADE_USDT", "10"))  # 每笔10U
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"

GATE_BASE = "https://api.gateio.ws/api/v4"
BINANCE_BASE = "https://api.binance.com"


def gate_sign(method, url, qs="", body=""):
    t = str(int(time.time()))
    hp = hashlib.sha512(body.encode()).hexdigest()
    sig = hmac.new(GATE_API_SECRET.encode(),
                   f"{method}\n{url}\n{qs}\n{hp}\n{t}".encode(),
                   hashlib.sha512).hexdigest()
    return {"KEY": GATE_API_KEY, "SIGN": sig, "TIMESTAMP": t, "Content-Type": "application/json"}


def gate_get(path, params=None):
    qs = "&".join(f"{k}={v}" for k, v in sorted(params.items())) if params else ""
    try:
        r = requests.get(GATE_BASE + path + ("?" + qs if qs else ""),
                         headers=gate_sign("GET", path, qs), timeout=10)
        return r.json()
    except Exception as e:
        print(f"[ERROR] Gate GET {path}: {e}")
        return None


def gate_post(path, data=None):
    body = json.dumps(data) if data else ""
    try:
        r = requests.post(GATE_BASE + path,
                          headers=gate_sign("POST", path, "", body),
                          data=body, timeout=10)
        return r.json()
    except Exception as e:
        print(f"[ERROR] Gate POST {path}: {e}")
        return None


def get_gate_price(pair):
    """获取 Gate.io 买一卖一价"""
    ob = gate_get("/spot/order_book", {"currency_pair": pair, "limit": 1})
    if ob and "bids" in ob and "asks" in ob:
        bid = float(ob["bids"][0][0]) if ob["bids"] else None
        ask = float(ob["asks"][0][0]) if ob["asks"] else None
        return bid, ask
    return None, None


def get_binance_price(symbol):
    """获取 Binance 买一卖一价"""
    try:
        r = requests.get(f"{BINANCE_BASE}/api/v3/ticker/bookTicker",
                         params={"symbol": symbol}, timeout=10)
        if r.status_code == 200:
            d = r.json()
            return float(d["bidPrice"]), float(d["askPrice"])
    except Exception as e:
        print(f"[ERROR] Binance {symbol}: {e}")
    return None, None


def place_gate_order(pair, side, amount, price):
    """在 Gate.io 下单"""
    data = {
        "currency_pair": pair,
        "side": side,
        "amount": str(amount),
        "price": str(price),
        "type": "limit",
        "time_in_force": "ioc"  # 立即成交否则取消
    }
    if DRY_RUN:
        print(f"  [DRY_RUN] {side.upper()} {amount} {pair} @ {price}")
        return {"id": "dry_run"}
    print(f"  [ORDER] {side.upper()} {amount} {pair} @ {price}")
    return gate_post("/spot/orders", data)


def scan():
    print(f"\n{'='*60}")
    print(f"[SCAN] {datetime.now().isoformat()}")
    print(f"{'='*60}")

    for pair_info in PAIRS:
        sym = pair_info["symbol"]
        gp = pair_info["gate_pair"]
        bs = pair_info["binance_symbol"]

        print(f"\n📊 {sym}")

        # 获取两边价格
        g_bid, g_ask = get_gate_price(gp)
        b_bid, b_ask = get_binance_price(bs)

        if not all([g_bid, g_ask, b_bid, b_ask]):
            print(f"  ⚠️ 无法获取价格，跳过")
            continue

        print(f"  Gate:  买 {g_bid:.2f}  卖 {g_ask:.2f}")
        print(f"  Binance: 买 {b_bid:.2f}  卖 {b_ask:.2f}")

        # 套利机会判断
        # 方向1: Gate买 → Binance卖 (Gate Ask < Binance Bid)
        profit1 = (b_bid - g_ask) / g_ask * 100
        # 方向2: Binance买 → Gate卖 (Binance Ask < Gate Bid)
        profit2 = (g_bid - b_ask) / b_ask * 100

        print(f"  Gate买→Binance卖: {profit1:.3f}%")
        print(f"  Binance买→Gate卖: {profit2:.3f}%")

        trades = []

        if profit1 > MIN_PROFIT_PERCENT:
            # 在Gate买入，在Binance卖出(通过Gate提币到Binance，或者直接两边下单)
            amount = TRADE_USDT / g_ask
            print(f"  🟢 套利机会! Gate买→Binance卖 利润{profit1:.2f}%")
            if DRY_RUN:
                print(f"  [DRY_RUN] 买入 {amount:.4f} {sym} @ Gate {g_ask}")
            trades.append({
                "direction": "Gate→Binance",
                "profit_pct": round(profit1, 3),
                "amount": round(amount, 4),
                "gate_price": g_ask,
                "binance_price": b_bid
            })

        if profit2 > MIN_PROFIT_PERCENT:
            amount = TRADE_USDT / b_ask
            print(f"  🟢 套利机会! Binance买→Gate卖 利润{profit2:.2f}%")
            if DRY_RUN:
                print(f"  [DRY_RUN] 买入 {amount:.4f} {sym} @ Binance {b_ask}")
            trades.append({
                "direction": "Binance→Gate",
                "profit_pct": round(profit2, 3),
                "amount": round(amount, 4),
                "binance_price": b_ask,
                "gate_price": g_bid
            })

        if not trades:
            print(f"  ❌ 无套利机会")

    print(f"\n[SCAN DONE] {datetime.now().isoformat()}")


if __name__ == "__main__":
    print("=== 跨交易所搬砖套利机器人 ===")
    print(f"最小利润阈值: {MIN_PROFIT_PERCENT}%")
    print(f"每笔交易: {TRADE_USDT} USDT")
    print(f"DRY_RUN: {DRY_RUN}")
    print()
    scan()
    print("\nDone.")