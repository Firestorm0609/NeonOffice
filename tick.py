#!/usr/bin/env python3
"""Prediction Market Agent — scans Polymarket, analyzes with Mistral, paper trades."""
from dotenv import load_dotenv
load_dotenv()

import os, json, time, random
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
STATE_FILE = DATA_DIR / "agent_state.json"
PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
TRADES_FILE = DATA_DIR / "trades.jsonl"

STATION_POSITIONS = {
    "center": {"x": 50, "y": 65}, "left_monitor": {"x": 16, "y": 72},
    "right_monitor": {"x": 84, "y": 72}, "center_screen": {"x": 50, "y": 68},
    "whiteboard": {"x": 46, "y": 22}, "coffee": {"x": 74, "y": 66},
    "server": {"x": 6, "y": 64},
}

STARTING_BALANCE = 100.0  # $10K paper money

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"cash": STARTING_BALANCE, "positions": {}, "total_trades": 0, "mood": "idle",
            "current_station": "center", "last_action": "none", "thought": "Waking up...",
            "portfolio_value": STARTING_BALANCE, "pnl": 0, "pnl_pct": 0,
            "robot_x": 50, "robot_y": 65, "_cycle_num": 0, "_last_station": "center",
            "active_markets": [], "category": "trending"}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def log_trade(trade):
    with open(TRADES_FILE, "a") as f:
        f.write(json.dumps(trade) + "\n")

def move_to(station, state, mood, thought):
    state["current_station"] = station
    state["mood"] = mood
    state["thought"] = thought
    pos = STATION_POSITIONS.get(station, STATION_POSITIONS["center"])
    state["robot_x"] = pos["x"]
    state["robot_y"] = pos["y"]

def fetch_markets(category="trending", limit=8):
    """Fetch markets from Polymarket."""
    from polymarket import get_trending, get_crypto_markets, get_politics_markets
    if category == "crypto":
        return get_crypto_markets()[:limit]
    elif category == "politics":
        return get_politics_markets()[:limit]
    else:
        return get_trending(limit)

def ask_mistral(prompt):
    from openai import OpenAI
    key = os.getenv("MISTRAL_API_KEY", "")
    client = OpenAI(api_key=key, base_url="https://api.mistral.ai/v1", timeout=12.0)
    r = client.chat.completions.create(model="mistral-small-latest",
        messages=[{"role": "system", "content": """You are a prediction market analyst. You analyze events and decide probability outcomes.

Reply with EXACTLY this format:
ACTION: <BUY_YES|BUY_NO|SELL|SKIP|RESEARCH>
MARKET: <market question, abbreviated>
AMOUNT: $<dollar amount to bet, max 20% of portfolio>
CONFIDENCE: <LOW|MEDIUM|HIGH>
REASON: <one sentence why>"""}, {"role": "user", "content": prompt}],
        max_tokens=200, temperature=0.7)
    return r.choices[0].message.content or ""

def parse_decision(response):
    result = {"action": "skip", "market": "", "amount": 0, "confidence": "LOW", "reason": ""}
    for line in response.split("\n"):
        line = line.strip()
        upper = line.upper()
        if upper.startswith("ACTION:"):
            content = line.split(":", 1)[1].strip().upper()
            if "BUY_YES" in content: result["action"] = "buy_yes"
            elif "BUY_NO" in content: result["action"] = "buy_no"
            elif "SELL" in content: result["action"] = "sell"
            elif "RESEARCH" in content: result["action"] = "research"
            else: result["action"] = "skip"
        elif upper.startswith("MARKET:"):
            result["market"] = line.split(":", 1)[1].strip()
        elif upper.startswith("AMOUNT:"):
            try:
                amt = line.split(":", 1)[1].strip().replace("$", "").replace(",", "")
                result["amount"] = float(amt)
            except: pass
        elif upper.startswith("CONFIDENCE:"):
            result["confidence"] = line.split(":", 1)[1].strip().upper()
        elif upper.startswith("REASON:"):
            result["reason"] = line.split(":", 1)[1].strip()
    return result

def execute_paper_trade(state, decision, markets):
    """Execute a paper trade on a prediction market."""
    # Find the market
    market = None
    for m in markets:
        if decision["market"].lower()[:30] in m["question"].lower() or m["question"].lower()[:30] in decision["market"].lower():
            market = m
            break
    
    if not market:
        return f"Market not found: {decision['market'][:40]}"
    
    amount = min(decision["amount"], state["cash"] * 0.2)  # Max 20% per trade
    if amount < 1:
        return "Amount too small"
    
    if decision["action"] == "buy_yes":
        shares = amount / market["yes_price"] if market["yes_price"] > 0 else 0
        if shares <= 0: return "Invalid price"
        state["cash"] -= amount
        key = f"YES_{market['id'][:8]}"
        if key in state["positions"]:
            pos = state["positions"][key]
            old_cost = pos["shares"] * pos["avg_price"]
            pos["shares"] += shares
            pos["avg_price"] = (old_cost + amount) / pos["shares"]
        else:
            state["positions"][key] = {
                "shares": shares, "avg_price": market["yes_price"],
                "side": "YES", "question": market["question"][:60],
                "market_id": market["id"], "current_price": market["yes_price"],
            }
        state["total_trades"] += 1
        log_trade({"action": "BUY YES", "market": market["question"][:60], "amount": amount,
                    "price": market["yes_price"], "shares": shares, "time": datetime.now().isoformat()})
        return f"Bought {shares:.0f} YES shares on '{market['question'][:40]}' @ ${market['yes_price']:.3f} (${amount:.2f})"
    
    elif decision["action"] == "buy_no":
        shares = amount / market["no_price"] if market["no_price"] > 0 else 0
        if shares <= 0: return "Invalid price"
        state["cash"] -= amount
        key = f"NO_{market['id'][:8]}"
        if key in state["positions"]:
            pos = state["positions"][key]
            old_cost = pos["shares"] * pos["avg_price"]
            pos["shares"] += shares
            pos["avg_price"] = (old_cost + amount) / pos["shares"]
        else:
            state["positions"][key] = {
                "shares": shares, "avg_price": market["no_price"],
                "side": "NO", "question": market["question"][:60],
                "market_id": market["id"], "current_price": market["no_price"],
            }
        state["total_trades"] += 1
        log_trade({"action": "BUY NO", "market": market["question"][:60], "amount": amount,
                    "price": market["no_price"], "shares": shares, "time": datetime.now().isoformat()})
        return f"Bought {shares:.0f} NO shares on '{market['question'][:40]}' @ ${market['no_price']:.3f} (${amount:.2f})"
    
    elif decision["action"] == "sell":
        # Find and sell position
        for key, pos in list(state["positions"].items()):
            if decision["market"].lower()[:30] in pos.get("question", "").lower():
                sell_price = pos.get("current_price", pos["avg_price"])
                proceeds = pos["shares"] * sell_price
                state["cash"] += proceeds
                pnl = proceeds - (pos["shares"] * pos["avg_price"])
                del state["positions"][key]
                state["total_trades"] += 1
                log_trade({"action": "SELL", "market": pos["question"][:60], "amount": proceeds,
                            "pnl": pnl, "time": datetime.now().isoformat()})
                return f"Sold position on '{pos['question'][:40]}' for ${proceeds:.2f} (PnL: ${pnl:+.2f})"
        return "No position found to sell"
    
    return f"Action: {decision['action']}"

def update_portfolio(state, markets):
    """Update portfolio value with current market prices."""
    total = state["cash"]
    for key, pos in state["positions"].items():
        # Find current price from markets
        for m in markets:
            if pos.get("market_id") == m["id"]:
                if pos["side"] == "YES":
                    pos["current_price"] = m["yes_price"]
                else:
                    pos["current_price"] = m["no_price"]
                break
        pos["value"] = pos["shares"] * pos.get("current_price", pos["avg_price"])
        total += pos["value"]
    state["portfolio_value"] = total
    state["pnl"] = total - STARTING_BALANCE
    state["pnl_pct"] = (state["pnl"] / STARTING_BALANCE) * 100

def run_one_cycle():
    state = load_state()
    cycle = state.get("_cycle_num", 0) + 1
    state["_cycle_num"] = cycle
    
    # Rotate categories
    categories = ["trending", "crypto", "politics", "trending", "crypto"]
    state["category"] = categories[cycle % len(categories)]
    
    # Step 1: Scan markets (left monitor)
    move_to("left_monitor", state, "scanning", f"Scanning {state['category']} markets...")
    save_state(state)
    markets = fetch_markets(state["category"])
    state["active_markets"] = [{"q": m["question"][:50], "yes": m["yes_price"], "vol": m["volume_24h"]} for m in markets[:5]]
    update_portfolio(state, markets)
    
    # Step 2: Think (center)
    move_to("center", state, "thinking", "Analyzing prediction opportunities...")
    save_state(state)
    
    # Step 3: Ask Mistral to analyze
    holdings_text = "None" if not state["positions"] else ", ".join(
        f"{p['side']} on '{p['question'][:30]}' ({p['shares']:.0f} sh @ ${p['avg_price']:.3f})" 
        for p in state["positions"].values())
    
    markets_text = "\n".join([
        f"  {i+1}. {m['question'][:60]}  YES: ${m['yes_price']:.3f}  NO: ${m['no_price']:.3f}  Vol: ${m['volume_24h']:,.0f}"
        for i, m in enumerate(markets[:6])
    ])
    
    prompt = f"""Cash: ${state['cash']:.2f} | Portfolio: ${state['portfolio_value']:.2f} | PnL: ${state['pnl']:.2f}
Open positions: {holdings_text}

Active {state['category']} markets:
{markets_text}

Analyze these prediction markets. Look for:
1. Events where you think the crowd is wrong about probability
2. High-volume markets with good liquidity
3. Events you can research and form an opinion on

Decide: buy YES, buy NO, sell a position, research more, or skip this cycle."""
    
    try:
        decision_text = ask_mistral(prompt)
    except Exception as e:
        decision_text = "ACTION: SKIP\nREASON: API error"
    
    decision = parse_decision(decision_text)
    
    # Step 4: Execute or visit station
    if decision["action"] in ["buy_yes", "buy_no", "sell"]:
        move_to("center_screen", state, "trading", f"Placing: {decision['action']} — {decision['reason'][:50]}")
        save_state(state)
        time.sleep(1)
        result = execute_paper_trade(state, decision, markets)
        state["last_action"] = result
        state["thought"] = result
    elif decision["action"] == "research":
        move_to("whiteboard", state, "researching", f"Researching: {decision['market'][:50] or 'market trends'}")
        state["thought"] = decision.get("reason", "Deep-diving into event data...")
    else:
        # Vary station based on cycle
        stations = ["whiteboard", "right_monitor", "server", "coffee", "center"]
        station = stations[cycle % len(stations)]
        mood_map = {"whiteboard": "analyzing", "right_monitor": "checking", 
                    "server": "diagnostics", "coffee": "resting", "center": "thinking"}
        move_to(station, state, mood_map.get(station, "idle"), decision.get("reason", "Considering next move..."))
    
    state["_last_station"] = state["current_station"]
    save_state(state)
    
    # Print summary
    positions_val = sum(p.get("value", 0) for p in state["positions"].values())
    print(f"  Cycle {cycle} | {state['category']} | {len(markets)} markets | {len(state['positions'])} positions")
    print(f"  Cash: ${state['cash']:.2f} | Positions: ${positions_val:.2f} | Total: ${state['portfolio_value']:.2f}")
    print(f"  Station: {state['current_station']} | {decision['action']} | {state['thought'][:60]}")

if __name__ == "__main__":
    run_one_cycle()
