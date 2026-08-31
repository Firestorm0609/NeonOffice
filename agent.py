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
    "center": {"x": 48, "y": 55},
    "left_monitor": {"x": 14, "y": 45},
    "right_monitor": {"x": 78, "y": 45},
    "center_screen": {"x": 48, "y": 48},
    "whiteboard": {"x": 46, "y": 25},
    "coffee": {"x": 72, "y": 55},
    "server": {"x": 6, "y": 40},
}

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"cash": STARTING_BALANCE, "holdings": {}, "total_trades": 0, "mood": "idle",
            "current_station": "center", "last_action": "none", "thought": "Waking up...",
            "portfolio_value": STARTING_BALANCE, "pnl": 0, "pnl_pct": 0,
            "robot_x": 48, "robot_y": 55}

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
            max_tokens=500, temperature=0.7)
        return response.choices[0].message.content or ""
    except Exception as e:
        return f"Error: {e}"

def decide_action(state, prices):
    holdings_text = "None" if not state["holdings"] else "\n".join([
        f"  {k}: {v['amount']:.4f} @ ${v['price']:.6f} = ${v['value']:.2f}"
        for k, v in state["holdings"].items()])
    prices_text = "\n".join([
        f"  {name}: ${p['price']:.6f} ({p['change_24h']:+.1f}%) Vol: ${p['volume']:,.0f}"
        for name, p in prices.items()])
    prompt = f"""Current state:
Cash: ${state['cash']:.2f} | Portfolio: ${state['portfolio_value']:.2f} | PnL: ${state['pnl']:.2f}
Holdings: {holdings_text}
Prices: {prices_text}

You are an autonomous trading agent. What should you do?
Options: SCAN, ANALYZE, TRADE, CHECK, REST, THINK

For trade: TRADE: BUY <TOKEN> $<AMOUNT> or TRADE: SELL <TOKEN> $<AMOUNT>
For others: ACTION: <SCAN|ANALYZE|CHECK|REST|THINK>
THOUGHT: <what you're thinking>"""
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
    for action in ["SCAN", "ANALYZE", "CHECK", "REST", "THINK"]:
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

def run_agent():
    state = load_state()
    cycle = 0
    print("\n" + "="*50)
    print("NEON OFFICE — Autonomous Agent Starting")
    print("="*50 + "\n")
    while True:
        cycle += 1
        now = datetime.now().strftime("%H:%M:%S")
        print(f"\n[Cycle {cycle}] {now}")
        
        # Scan prices
        print("  Scanning prices...")
        state["current_station"] = "left_monitor"
        state["mood"] = "scanning"
        state["thought"] = "Checking market prices..."
        pos = STATION_POSITIONS["left_monitor"]
        state["robot_x"] = pos["x"]
        state["robot_y"] = pos["y"]
        save_state(state)
        time.sleep(2)
        
        prices = get_all_prices()
        update_portfolio(state, prices)
        for name, p in prices.items():
            print(f"    {name}: ${p['price']:.6f} ({p['change_24h']:+.1f}%)")
        
        # Decide
        print("  Thinking...")
        state["current_station"] = "center"
        state["mood"] = "thinking"
        state["thought"] = "Analyzing market conditions..."
        pos = STATION_POSITIONS["center"]
        state["robot_x"] = pos["x"]
        state["robot_y"] = pos["y"]
        save_state(state)
        time.sleep(2)
        
        decision = decide_action(state, prices)
        print(f"  Decision: {decision[:100]}...")
        parsed = parse_decision(decision)
        
        # Execute
        if parsed["type"] == "trade":
            print(f"  Trading: {parsed['action']} ${parsed['amount']:.2f} {parsed['token']}")
            state["current_station"] = "center_screen"
            state["mood"] = "trading"
            state["thought"] = f"Executing: {parsed['action']} {parsed['token']}..."
            pos = STATION_POSITIONS["center_screen"]
            state["robot_x"] = pos["x"]
            state["robot_y"] = pos["y"]
            save_state(state)
            time.sleep(3)
            result = execute_trade(state, parsed["action"], parsed["token"], parsed["amount"])
            print(f"  Result: {result}")
            state["last_action"] = result
            state["thought"] = result
        elif parsed["type"] == "scan":
            state["current_station"] = "left_monitor"
            state["mood"] = "scanning"
            state["thought"] = parsed.get("thought", "Checking prices...")
            pos = STATION_POSITIONS["left_monitor"]
            state["robot_x"] = pos["x"]
            state["robot_y"] = pos["y"]
        elif parsed["type"] == "analyze":
            state["current_station"] = "whiteboard"
            state["mood"] = "analyzing"
            state["thought"] = parsed.get("thought", "Thinking about strategy...")
            pos = STATION_POSITIONS["whiteboard"]
            state["robot_x"] = pos["x"]
            state["robot_y"] = pos["y"]
        elif parsed["type"] == "check":
            state["current_station"] = "right_monitor"
            state["mood"] = "checking"
            state["thought"] = f"Portfolio: ${state['portfolio_value']:.2f}"
            pos = STATION_POSITIONS["right_monitor"]
            state["robot_x"] = pos["x"]
            state["robot_y"] = pos["y"]
        elif parsed["type"] == "rest":
            state["current_station"] = "coffee"
            state["mood"] = "resting"
            state["thought"] = "Taking a break..."
            pos = STATION_POSITIONS["coffee"]
            state["robot_x"] = pos["x"]
            state["robot_y"] = pos["y"]
            save_state(state)
            time.sleep(10)
        elif parsed["type"] == "think":
            state["current_station"] = "center"
            state["mood"] = "thinking"
            state["thought"] = parsed.get("thought", "Contemplating...")
            pos = STATION_POSITIONS["center"]
            state["robot_x"] = pos["x"]
            state["robot_y"] = pos["y"]
        
        save_state(state)
        print(f"  Portfolio: ${state['portfolio_value']:.2f} (PnL: ${state['pnl']:.2f})")
        print(f"  Station: {state['current_station']} | Mood: {state['mood']}")
        
        wait = random.randint(15, 30)
        print(f"  Waiting {wait}s...")
        time.sleep(wait)

if __name__ == "__main__":
    run_agent()
