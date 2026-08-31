#!/usr/bin/env python3
"""Run one agent cycle and exit. Called by cron every 30 seconds."""
from dotenv import load_dotenv
load_dotenv()

import os, json, time, random
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
STATE_FILE = DATA_DIR / "agent_state.json"

STATION_POSITIONS = {
    "center": {"x": 48, "y": 62}, "left_monitor": {"x": 16, "y": 72},
    "right_monitor": {"x": 84, "y": 72}, "center_screen": {"x": 48, "y": 68},
    "whiteboard": {"x": 46, "y": 22}, "coffee": {"x": 74, "y": 66},
    "server": {"x": 6, "y": 64},
}

STARTING_BALANCE = 100000.0
TOKENS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "POPCAT": "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
    "TRUMP": "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN",
    "FARTCOIN": "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump",
}

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"cash": STARTING_BALANCE, "holdings": {}, "total_trades": 0, "mood": "idle",
            "current_station": "center", "last_action": "none", "thought": "Waking up...",
            "portfolio_value": STARTING_BALANCE, "pnl": 0, "pnl_pct": 0,
            "robot_x": 48, "robot_y": 62, "_cycle_num": 0, "_last_station": "center"}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def move_to(station, state, mood, thought):
    state["current_station"] = station
    state["mood"] = mood
    state["thought"] = thought
    pos = STATION_POSITIONS.get(station, STATION_POSITIONS["center"])
    state["robot_x"] = pos["x"]
    state["robot_y"] = pos["y"]

def get_prices():
    import httpx
    prices = {}
    for name, addr in TOKENS.items():
        try:
            r = httpx.get(f"https://api.dexscreener.com/latest/dex/tokens/{addr}", timeout=8)
            if r.status_code == 200:
                pairs = r.json().get("pairs", [])
                if pairs:
                    p = pairs[0]
                    prices[name] = {
                        "price": float(p.get("priceUsd", "0")),
                        "change_24h": float(p.get("priceChange", {}).get("h24", "0")),
                        "volume": float(p.get("volume", {}).get("h24", 0)),
                    }
        except:
            pass
    return prices

def ask_mistral(prompt):
    from openai import OpenAI
    key = os.getenv("MISTRAL_API_KEY", "")
    client = OpenAI(api_key=key, base_url="https://api.mistral.ai/v1", timeout=10.0)
    r = client.chat.completions.create(model="mistral-small-latest",
        messages=[{"role": "system", "content": "You are a crypto trading agent. Reply ONLY with ACTION: and THOUGHT: lines."},
                  {"role": "user", "content": prompt}],
        max_tokens=150, temperature=0.7)
    return r.choices[0].message.content or ""

def run_one_cycle():
    state = load_state()
    cycle = state.get("_cycle_num", 0) + 1
    state["_cycle_num"] = cycle
    
    # Step 1: Scan
    move_to("left_monitor", state, "scanning", "Fetching live market data...")
    save_state(state)
    prices = get_prices()
    
    # Update portfolio
    total = state["cash"]
    for tok, h in state["holdings"].items():
        if tok in prices:
            h["price"] = prices[tok]["price"]
            h["value"] = h["amount"] * h["price"]
        total += h.get("value", 0)
    state["portfolio_value"] = total
    state["pnl"] = total - STARTING_BALANCE
    state["pnl_pct"] = (state["pnl"] / STARTING_BALANCE) * 100
    
    # Step 2: Think
    move_to("center", state, "thinking", "Analyzing opportunities...")
    save_state(state)
    
    # Step 3: Ask LLM
    holdings_text = "None" if not state["holdings"] else ", ".join(
        f"{k}: ${v.get('value',0):.0f}" for k, v in state["holdings"].items())
    prices_text = ", ".join(f"{n}: ${p['price']:.4f} ({p['change_24h']:+.1f}%)" 
                           for n, p in prices.items())
    
    prompt = f"""Cash: ${state['cash']:.0f} | Portfolio: ${state['portfolio_value']:.0f} | PnL: ${state['pnl']:.0f}
Holdings: {holdings_text}
Prices: {prices_text}
Cycle: {cycle} | Last: {state.get('_last_station','center')}

Pick NEXT station: SCAN, ANALYZE, TRADE, CHECK, SERVER, COFFEE, THINK
Every 3rd cycle visit SERVER. Every 5th visit COFFEE. Don't repeat last station.
For TRADE: ACTION: TRADE BUY <TOKEN> $<AMOUNT> or ACTION: TRADE SELL <TOKEN> $<AMOUNT>
Otherwise: ACTION: <STATION>
THOUGHT: <one sentence>"""

    try:
        decision = ask_mistral(prompt)
    except Exception as e:
        decision = "ACTION: THINK\nTHOUGHT: API error"
    
    # Parse
    action_type = "think"
    thought = "Contemplating..."
    trade_action = trade_token = trade_amount = None
    
    for line in decision.split("\n"):
        upper = line.upper().strip()
        if upper.startswith("ACTION:"):
            content = line.split(":", 1)[1].strip()
            if "TRADE" in content:
                parts = content.split()
                if len(parts) >= 4:
                    action_type = "trade"
                    trade_action = parts[1].upper()
                    trade_token = parts[2].upper()
                    try: trade_amount = float(parts[3].replace("$", ""))
                    except: action_type = "think"
            elif "SCAN" in content: action_type = "scan"
            elif "ANALYZE" in content: action_type = "analyze"
            elif "CHECK" in content: action_type = "check"
            elif "SERVER" in content: action_type = "server"
            elif "COFFEE" in content: action_type = "coffee"
            elif "THINK" in content: action_type = "think"
        elif upper.startswith("THOUGHT:"):
            thought = line.split(":", 1)[1].strip()
    
    # Step 4: Walk to station
    if action_type == "trade" and trade_action and trade_token:
        move_to("center_screen", state, "trading", f"Executing: {trade_action} {trade_token}...")
        save_state(state)
        time.sleep(2)
        price = prices.get(trade_token, {}).get("price", 0)
        if price > 0 and trade_amount:
            if trade_action == "BUY" and trade_amount <= state["cash"]:
                tokens = trade_amount / price
                state["cash"] -= trade_amount
                if trade_token in state["holdings"]:
                    h = state["holdings"][trade_token]
                    old_val = h["amount"] * h["price"]
                    h["amount"] += tokens
                    h["price"] = (old_val + trade_amount) / h["amount"]
                    h["value"] = h["amount"] * h["price"]
                else:
                    state["holdings"][trade_token] = {"amount": tokens, "price": price, "value": tokens * price}
                state["total_trades"] += 1
                thought = f"Bought {tokens:.2f} {trade_token} @ ${price:.6f}"
            elif trade_action == "SELL" and trade_token in state["holdings"]:
                h = state["holdings"][trade_token]
                tokens = min(trade_amount / price, h["amount"])
                amount = tokens * price
                state["cash"] += amount
                h["amount"] -= tokens
                if h["amount"] <= 0.0001: del state["holdings"][trade_token]
                else: h["value"] = h["amount"] * h["price"]
                state["total_trades"] += 1
                thought = f"Sold {tokens:.2f} {trade_token} @ ${price:.6f}"
            else:
                thought = f"Cannot {trade_action} {trade_token}"
        state["last_action"] = thought
    else:
        station_map = {"scan": "left_monitor", "analyze": "whiteboard", "check": "right_monitor",
                       "server": "server", "coffee": "coffee", "think": "center"}
        station = station_map.get(action_type, "center")
        mood_map = {"scan": "scanning", "analyze": "analyzing", "check": "checking",
                    "server": "diagnostics", "coffee": "resting", "think": "thinking"}
        move_to(station, state, mood_map.get(action_type, "idle"), thought)
    
    state["_last_station"] = state["current_station"]
    state["thought"] = thought
    save_state(state)

if __name__ == "__main__":
    run_one_cycle()
