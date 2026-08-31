"""
NeonOffice — Autonomous Trading Agent
"""

from dotenv import load_dotenv
load_dotenv()

import os
import json
import time
import random
from datetime import datetime
from pathlib import Path
from openai import OpenAI
import httpx

# Config
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
STATE_FILE = DATA_DIR / "agent_state.json"
TRADES_FILE = DATA_DIR / "trades.jsonl"

MISTRAL_KEY = os.getenv("MISTRAL_API_KEY", "")
client = OpenAI(api_key=MISTRAL_KEY, base_url="https://api.mistral.ai/v1", timeout=15.0)

TOKENS = {
    "SOL": {"address": "So11111111111111111111111111111111111111112"},
    "WIF": {"address": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"},
    "BONK": {"address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"},
    "POPCAT": {"address": "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"},
    "TRUMP": {"address": "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN"},
    "FARTCOIN": {"address": "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump"},
}
STARTING_BALANCE = 100000.0

STATION_POSITIONS = {
    "center": {"x": 48, "y": 52},
    "left_monitor": {"x": 17, "y": 40},
    "right_monitor": {"x": 81, "y": 40},
    "center_screen": {"x": 48, "y": 46},
    "whiteboard": {"x": 46, "y": 26},
    "coffee": {"x": 74, "y": 52},
    "server": {"x": 6, "y": 38},
}

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"cash": STARTING_BALANCE, "holdings": {}, "total_trades": 0, "mood": "idle",
            "current_station": "center", "last_action": "none", "thought": "Waking up...",
            "portfolio_value": STARTING_BALANCE, "pnl": 0, "pnl_pct": 0,
            "robot_x": 48, "robot_y": 52, "_cycle_num": 0, "_last_station": "center"}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def log_trade(trade):
    with open(TRADES_FILE, "a") as f:
        f.write(json.dumps(trade) + "\n")

def get_price(token_name):
    if token_name not in TOKENS:
        return None
    url = f"https://api.dexscreener.com/latest/dex/tokens/{TOKENS[token_name]['address']}"
    try:
        with httpx.Client(timeout=10) as http:
            resp = http.get(url)
            if resp.status_code == 200:
                pairs = resp.json().get("pairs", [])
                if pairs:
                    p = pairs[0]
                    return {"symbol": token_name, "price": float(p.get("priceUsd", "0")),
                            "change_24h": float(p.get("priceChange", {}).get("h24", "0")),
                            "volume": float(p.get("volume", {}).get("h24", 0)),
                            "liquidity": float(p.get("liquidity", {}).get("usd", 0))}
    except Exception as e:
        print(f"  Price error: {e}")
    return None

def get_all_prices():
    prices = {}
    for name in TOKENS:
        p = get_price(name)
        if p:
            prices[name] = p
    return prices

def ask_mistral(prompt, system="You are a crypto trading agent. Be concise."):
    try:
        response = client.chat.completions.create(model="mistral-small-latest",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=300, temperature=0.7)
        return response.choices[0].message.content or ""
    except Exception as e:
        print(f"  Mistral error: {e}")
        return "ACTION: THINK\nTHOUGHT: API error, will retry next cycle"

def decide_action(state, prices):
    holdings_text = "None" if not state["holdings"] else "\n".join([
        f"  {k}: {v['amount']:.4f} @ ${v['price']:.6f} = ${v['value']:.2f}"
        for k, v in state["holdings"].items()])
    prices_text = "\n".join([
        f"  {name}: ${p['price']:.6f} ({p['change_24h']:+.1f}%) Vol: ${p['volume']:,.0f}"
        for name, p in prices.items()])

    cycle = state.get("_cycle_num", 0)
    last = state.get("_last_station", "center")

    prompt = f"""You are an autonomous trading agent in a neon office. You move between stations.

Cash: ${state['cash']:.2f} | Portfolio: ${state['portfolio_value']:.2f} | PnL: ${state['pnl']:.2f}
Holdings: {holdings_text}
Prices: {prices_text}
Cycle: {cycle} | Last station: {last}

STATIONS (pick one):
- SCAN: Left monitor — check live prices
- ANALYZE: Whiteboard — write your trading strategy
- TRADE: Center screen — execute buy/sell
- CHECK: Right monitor — review portfolio
- SERVER: Server rack — check system health
- COFFEE: Coffee machine — take a short break
- THINK: Center desk — ponder the market

RULES:
1. Every cycle starts at the left monitor (you already scanned prices)
2. Pick your NEXT station wisely — rotate between different ones
3. Every 3rd cycle: visit SERVER
4. Every 5th cycle: visit COFFEE
5. Don't repeat the same station twice in a row
6. Only TRADE when you see a clear opportunity

Reply with EXACTLY this format:
ACTION: <SCAN|ANALYZE|TRADE|CHECK|SERVER|COFFEE|THINK>
THOUGHT: <one short sentence>

For TRADE use: ACTION: TRADE BUY <TOKEN> $<AMOUNT> or ACTION: TRADE SELL <TOKEN> $<AMOUNT>"""
    return ask_mistral(prompt)

def parse_decision(response):
    response_upper = response.upper()
    if "TRADE:" in response_upper:
        for line in response.split("\n"):
            if "TRADE:" in line.upper():
                parts = line.split(":", 1)[1].strip().split()
                if len(parts) >= 3:
                    try:
                        return {"type": "trade", "action": parts[0].upper(), "token": parts[1].upper(), "amount": float(parts[2].replace("$", ""))}
                    except: pass
    for action in ["SCAN", "ANALYZE", "CHECK", "SERVER", "COFFEE", "REST", "THINK"]:
        if action in response_upper:
            thought = response.split("THOUGHT:")[1].strip() if "THOUGHT:" in response else ""
            return {"type": action.lower(), "thought": thought}
    return {"type": "scan", "thought": "Checking market..."}

def execute_trade(state, action, token, amount):
    prices = get_all_prices()
    if token not in prices:
        return f"Token {token} not found"
    price = prices[token]["price"]
    if action == "BUY":
        if amount > state["cash"]:
            return f"Not enough cash"
        tokens_bought = amount / price
        state["cash"] -= amount
        if token in state["holdings"]:
            h = state["holdings"][token]
            old_val = h["amount"] * h["price"]
            h["amount"] += tokens_bought
            h["price"] = (old_val + amount) / h["amount"]
            h["value"] = h["amount"] * h["price"]
        else:
            state["holdings"][token] = {"amount": tokens_bought, "price": price, "value": tokens_bought * price}
        state["total_trades"] += 1
        log_trade({"action": "BUY", "token": token, "amount_usd": amount, "price": price, "time": datetime.now().isoformat()})
        return f"Bought {tokens_bought:.4f} {token} @ ${price:.6f}"
    elif action == "SELL":
        if token not in state["holdings"]:
            return f"No {token} to sell"
        h = state["holdings"][token]
        max_sell = h["amount"] * price
        if amount > max_sell: amount = max_sell
        tokens_sold = amount / price
        state["cash"] += amount
        h["amount"] -= tokens_sold
        if h["amount"] <= 0.0001: del state["holdings"][token]
        else: h["value"] = h["amount"] * h["price"]
        state["total_trades"] += 1
        log_trade({"action": "SELL", "token": token, "amount_usd": amount, "price": price, "time": datetime.now().isoformat()})
        return f"Sold {tokens_sold:.4f} {token} @ ${price:.6f}"
    return "Unknown action"

def update_portfolio(state, prices):
    total = state["cash"]
    for token, h in state["holdings"].items():
        if token in prices:
            h["price"] = prices[token]["price"]
            h["value"] = h["amount"] * h["price"]
        total += h.get("value", 0)
    state["portfolio_value"] = total
    state["pnl"] = total - STARTING_BALANCE
    state["pnl_pct"] = (state["pnl"] / STARTING_BALANCE) * 100

def move_to(station, state, mood="idle", thought=""):
    """Move robot to a station and update state."""
    state["current_station"] = station
    state["mood"] = mood
    state["thought"] = thought
    pos = STATION_POSITIONS.get(station, STATION_POSITIONS["center"])
    state["robot_x"] = pos["x"]
    state["robot_y"] = pos["y"]

def run_agent():
    state = load_state()
    cycle = 0
    print("\n" + "="*50)
    print("NEON OFFICE — Autonomous Agent Starting")
    print("="*50 + "\n", flush=True)
    while True:
        try:
            cycle += 1
            state["_cycle_num"] = cycle
            now = datetime.now().strftime("%H:%M:%S")
            print(f"\n[Cycle {cycle}] {now}", flush=True)

            # ── Step 1: Always scan prices first ──
            move_to("left_monitor", state, "scanning", "Fetching live market data...")
            save_state(state)
            time.sleep(1)

            prices = get_all_prices()
            update_portfolio(state, prices)
            for name, p in prices.items():
                print(f"    {name}: ${p['price']:.6f} ({p['change_24h']:+.1f}%)", flush=True)

            # ── Step 2: Think at center ──
            move_to("center", state, "thinking", "Analyzing opportunities...")
            save_state(state)
            time.sleep(1)

            # ── Step 3: Ask LLM what to do next ──
            decision = decide_action(state, prices)
            print(f"  Decision: {decision[:150]}...", flush=True)
            parsed = parse_decision(decision)
            state["_last_station"] = "center"

            # ── Step 4: Walk to chosen station ──
            if parsed["type"] == "trade":
                print(f"  Trading: {parsed['action']} ${parsed['amount']:.2f} {parsed['token']}", flush=True)
                move_to("center_screen", state, "trading", f"Executing: {parsed['action']} {parsed['token']}...")
                save_state(state)
                time.sleep(2)
                result = execute_trade(state, parsed["action"], parsed["token"], parsed["amount"])
                print(f"  Result: {result}", flush=True)
                state["last_action"] = result
                state["thought"] = result
                state["_last_station"] = "center_screen"

            elif parsed["type"] == "scan":
                move_to("left_monitor", state, "scanning", parsed.get("thought", "Deep scan..."))
                state["_last_station"] = "left_monitor"

            elif parsed["type"] == "analyze":
                move_to("whiteboard", state, "analyzing", parsed.get("thought", "Writing strategy..."))
                state["_last_station"] = "whiteboard"

            elif parsed["type"] == "check":
                move_to("right_monitor", state, "checking", parsed.get("thought", f"Portfolio: ${state['portfolio_value']:.2f}"))
                state["_last_station"] = "right_monitor"

            elif parsed["type"] == "server":
                move_to("server", state, "diagnostics", "Checking system health... 10 keys active, 99.9% uptime")
                state["_last_station"] = "server"

            elif parsed["type"] in ["rest", "coffee"]:
                move_to("coffee", state, "resting", "Taking a coffee break...")
                save_state(state)
                time.sleep(3)
                state["_last_station"] = "coffee"

            elif parsed["type"] == "think":
                move_to("center", state, "thinking", parsed.get("thought", "Contemplating..."))
                state["_last_station"] = "center"

            else:
                fallbacks = ["left_monitor", "whiteboard", "right_monitor", "center", "server", "coffee"]
                station = fallbacks[cycle % len(fallbacks)]
                move_to(station, state, "idle", "Moving to next station...")
                state["_last_station"] = station

            save_state(state)
            print(f"  Portfolio: ${state['portfolio_value']:.2f} (PnL: ${state['pnl']:.2f})", flush=True)
            print(f"  Station: {state['current_station']} | Mood: {state['mood']}", flush=True)

            wait = random.randint(8, 15)
            print(f"  Waiting {wait}s...", flush=True)
            time.sleep(wait)

        except Exception as e:
            print(f"  ERROR: {e}", flush=True)
            import traceback
            traceback.print_exc()
            time.sleep(5)


if __name__ == "__main__":
    run_agent()
