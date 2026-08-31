#!/usr/bin/env python3
"""
Fully Autonomous Prediction Market Agent
- Scans Polymarket for opportunities
- Researches events via web
- Makes decisions with Mistral
- Learns from outcomes
- Modifies its own strategy
"""
from dotenv import load_dotenv
load_dotenv()

import os, json, time, random
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
STATE_FILE = DATA_DIR / "agent_state.json"

STATION_POSITIONS = {
    "center": {"x": 50, "y": 65}, "left_monitor": {"x": 16, "y": 72},
    "right_monitor": {"x": 84, "y": 72}, "center_screen": {"x": 50, "y": 68},
    "whiteboard": {"x": 46, "y": 22}, "coffee": {"x": 74, "y": 66},
    "server": {"x": 6, "y": 64},
}

STARTING_BALANCE = 100.0

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"cash": STARTING_BALANCE, "positions": {}, "total_trades": 0, "mood": "idle",
            "current_station": "center", "last_action": "none", "thought": "Waking up...",
            "portfolio_value": STARTING_BALANCE, "pnl": 0, "pnl_pct": 0,
            "robot_x": 50, "robot_y": 65, "_cycle_num": 0, "_last_station": "center",
            "active_markets": [], "category": "trending", "research_cache": {},
            "discovered_categories": ["crypto", "politics", "sports", "science", "entertainment"]}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def move_to(station, state, mood, thought):
    state["current_station"] = station
    state["mood"] = mood
    state["thought"] = thought
    pos = STATION_POSITIONS.get(station, STATION_POSITIONS["center"])
    state["robot_x"] = pos["x"]
    state["robot_y"] = pos["y"]

# ═══════════════════════════════════════════
#  FETCHING — what markets exist
# ═══════════════════════════════════════════
def fetch_markets(category=None, limit=10):
    from polymarket import get_markets
    tag = category if category and category != "trending" else None
    return get_markets(limit=limit, tag=tag, min_volume=2000)

def search_web(query):
    from research import search_news, web_search_and_summarize
    return web_search_and_summarize(query)

def research_market(market):
    """Deep research on a specific market — uses all free sources."""
    from research import research_topic, polymarket_description
    question = market.get("question", "")
    market_id = market.get("id", "")
    
    # Get Polymarket's own description
    desc_data = polymarket_description(market_id) if market_id else {}
    description = desc_data.get("description", "")
    
    # Full research: Google News + DuckDuckGo + CoinGecko
    result = research_topic(question, description)
    return {
        "question": question,
        "summary": result["summary"][:600],
        "news_count": len(result["news"]),
        "web_count": len(result["web"]),
        "yes_price": market.get("yes_price", 0),
        "volume": market.get("volume_24h", 0),
    }

# ═══════════════════════════════════════════
#  AI BRAIN — Mistral decides everything
# ═══════════════════════════════════════════
# Load all Mistral keys
_mistral_keys = []
for k, v in os.environ.items():
    if k.startswith("MISTRAL_API_KEY") and v.strip():
        _mistral_keys.append(v.strip())
if not _mistral_keys:
    _mistral_keys = [os.getenv("MISTRAL_API_KEY", "")]
_key_index = 0

def ask_mistral(prompt, system=None):
    global _key_index
    from openai import OpenAI
    last_error = None
    for attempt in range(len(_mistral_keys)):
        key = _mistral_keys[(_key_index + attempt) % len(_mistral_keys)]
        client = OpenAI(api_key=key, base_url="https://api.mistral.ai/v1", timeout=15.0)
        try:
            r = client.chat.completions.create(model="mistral-small-latest",
                messages=[{"role": "system", "content": system or "You are a prediction market trader. Reply with ACTION: and REASON: lines."}, {"role": "user", "content": prompt}],
                max_tokens=200, temperature=0.8)
            _key_index = (_key_index + attempt + 1) % len(_mistral_keys)
            return r.choices[0].message.content or ""
        except Exception as e:
            last_error = e
    return f"ACTION: THINK\nREASON: All {len(_mistral_keys)} keys failed: {last_error}"
    if not system:
        system = """You are a sharp prediction market trader. You have:
- Live Polymarket data (real markets, real prices)
- Web research (Google News, DuckDuckGo, CoinGecko)
- $100 paper trading account
- Memory of past wins and losses

YOUR EDGE: You research before you bet. You only bet when you have an informational advantage.

RULES:
1. Never bet more than 10% of cash on one market
2. Only bet when confidence is MEDIUM or HIGH
3. Research a market before betting on it
4. Sell positions that are losing — cut losses fast
5. If win rate is below 40%, be more conservative
6. Take breaks when nothing looks good

Reply with EXACTLY this format:
ACTION: <RESEARCH|BET_YES|BET_NO|SELL|SCAN|THINK|UPDATE_STRATEGY|BREAK>
TARGET: <market question or topic>
AMOUNT: $<amount, max 10% of cash>
CONFIDENCE: <LOW|MEDIUM|HIGH>
REASON: <one sentence why>"""


def parse_decision(response):
    result = {"action": "think", "target": "", "amount": 0, "confidence": "LOW", "reason": ""}
    for line in response.split("\n"):
        line = line.strip()
        upper = line.upper()
        if upper.startswith("ACTION:"):
            content = line.split(":", 1)[1].strip().upper()
            for act in ["RESEARCH", "BET_YES", "BET_NO", "SELL", "SCAN", "THINK", "UPDATE_STRATEGY", "BREAK"]:
                if act in content:
                    result["action"] = act.lower()
                    break
        elif upper.startswith("TARGET:"):
            result["target"] = line.split(":", 1)[1].strip()
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

# ═══════════════════════════════════════════
#  EXECUTION — carry out decisions
# ═══════════════════════════════════════════
def execute_trade(state, action, target, amount, markets):
    """Find a market and place a paper bet."""
    # Find matching market
    market = None
    for m in markets:
        if target.lower()[:25] in m["question"].lower() or m["question"].lower()[:25] in target.lower():
            market = m
            break
    if not market:
        # Try fuzzy match
        target_words = set(target.lower().split())
        for m in markets:
            q_words = set(m["question"].lower().split())
            if len(target_words & q_words) >= 3:
                market = m
                break
    if not market:
        return f"Market not found: {target[:40]}"
    
    # Cap bet at 20% of cash
    from memory import load_strategy
    strat = load_strategy()
    max_bet = state["cash"] * strat.get("max_bet_pct", 0.20)
    amount = min(amount, max_bet, state["cash"] * 0.20)
    if amount < 0.50:
        return "Amount too small"
    
    if action == "bet_yes":
        price = market["yes_price"]
        if price <= 0 or price >= 1: return "Invalid price"
        shares = amount / price
        state["cash"] -= amount
        key = f"Y_{market['id'][:8]}"
        state["positions"][key] = {
            "shares": shares, "avg_price": price, "side": "YES",
            "question": market["question"][:60], "market_id": market["id"],
            "current_price": price, "bet_amount": amount,
        }
        state["total_trades"] += 1
        return f"Bought {shares:.0f} YES on '{market['question'][:40]}' @ ${price:.3f} (${amount:.2f})"
    
    elif action == "bet_no":
        no_price = 1 - market["yes_price"]
        if no_price <= 0 or no_price >= 1: return "Invalid price"
        shares = amount / no_price
        state["cash"] -= amount
        key = f"N_{market['id'][:8]}"
        state["positions"][key] = {
            "shares": shares, "avg_price": no_price, "side": "NO",
            "question": market["question"][:60], "market_id": market["id"],
            "current_price": no_price, "bet_amount": amount,
        }
        state["total_trades"] += 1
        return f"Bought {shares:.0f} NO on '{market['question'][:40]}' @ ${no_price:.3f} (${amount:.2f})"
    
    elif action == "sell":
        for key, pos in list(state["positions"].items()):
            if target.lower()[:25] in pos.get("question", "").lower():
                sell_price = pos.get("current_price", pos["avg_price"])
                proceeds = pos["shares"] * sell_price
                state["cash"] += proceeds
                pnl = proceeds - pos["bet_amount"]
                del state["positions"][key]
                state["total_trades"] += 1
                from memory import record_decision, record_outcome
                record_outcome(len(load_memory()["decisions"]) - 1, pnl, pnl > 0)
                return f"Sold '{pos['question'][:40]}' for ${proceeds:.2f} (PnL: ${pnl:+.2f})"
        return "No position found to sell"
    
    return f"Unknown action: {action}"

def update_portfolio(state, markets):
    total = state["cash"]
    for key, pos in state["positions"].items():
        for m in markets:
            if pos.get("market_id") == m["id"]:
                if pos["side"] == "YES":
                    pos["current_price"] = m["yes_price"]
                else:
                    pos["current_price"] = 1 - m["yes_price"]
                break
        pos["value"] = pos["shares"] * pos.get("current_price", pos["avg_price"])
        total += pos.get("value", 0)
    state["portfolio_value"] = total
    state["pnl"] = total - STARTING_BALANCE
    state["pnl_pct"] = (state["pnl"] / STARTING_BALANCE) * 100

# ═══════════════════════════════════════════
#  MAIN LOOP — one autonomous cycle
# ═══════════════════════════════════════════
def run_one_cycle():
    from memory import load_memory, record_decision, get_performance_summary, self_modify_strategy, load_strategy
    state = load_state()
    mem = load_memory()
    strat = load_strategy()
    cycle = state.get("_cycle_num", 0) + 1
    state["_cycle_num"] = cycle
    
    # Step 1: Scan markets (left monitor)
    move_to("left_monitor", state, "scanning", "Scanning prediction markets...")
    save_state(state)
    
    # Fetch from multiple categories to discover variety
    all_markets = []
    cats = state.get("discovered_categories", ["crypto", "politics"])
    for cat in random.sample(cats, min(2, len(cats))):
        all_markets.extend(fetch_markets(cat, 5))
    # Deduplicate
    seen = set()
    markets = []
    for m in all_markets:
        if m["id"] not in seen:
            seen.add(m["id"])
            markets.append(m)
    markets = markets[:10]
    
    state["active_markets"] = [{"q": m["question"][:50], "yes": m["yes_price"], "vol": m["volume_24h"]} for m in markets[:5]]
    update_portfolio(state, markets)
    
    # Step 2: Get memory context
    perf = get_performance_summary()
    positions_summary = ", ".join([
        f"{p['side']} on '{p['question'][:25]}' (${p.get('bet_amount',0):.0f})"
        for p in state["positions"].values()
    ]) or "None"
    
    # Step 3: Ask Mistral — full autonomous decision
    move_to("center", state, "thinking", "Analyzing everything...")
    save_state(state)
    
    markets_text = "\n".join([
        f"  {m['question'][:55]}  YES: ${m['yes_price']:.3f}  Vol: ${m['volume_24h']:,.0f}"
        for m in markets[:6]
    ])
    
    prompt = f"""CYCLE {cycle} — AUTONOMOUS DECISION

CASH: ${state['cash']:.2f} | PORTFOLIO: ${state['portfolio_value']:.2f} | PnL: ${state['pnl']:+.2f}
POSITIONS: {positions_summary}

MARKETS:
{markets_text}

PAST PERFORMANCE:
  Wins: {perf['wins']} | Losses: {perf['losses']} | Win Rate: {perf['win_rate']}
  Total PnL: {perf['total_pnl']}
  Best categories: {json.dumps(perf['patterns'])}
  Recent learnings: {'; '.join([l['insight'] for l in perf['learnings'][-3:]]) or 'None yet'}

STRATEGY: Max bet {strat['max_bet_pct']:.0%} | Min vol ${strat['min_volume']:,} | Risk: {strat['risk_tolerance']}

You are autonomous. Decide what to do:
- RESEARCH a specific market deeper (web search for info)
- BET YES or BET NO on a market
- SELL a position that's doing well or poorly
- SCAN different categories
- THINK about your strategy
- UPDATE_STRATEGY if your approach needs changing
- BREAK if you need to rest

What do you do next?"""

    try:
        decision_text = ask_mistral(prompt)
    except Exception as e:
        decision_text = "ACTION: THINK\nREASON: Error"
    
    decision = parse_decision(decision_text)
    decision["category"] = state.get("category", "")
    
    # Step 4: Execute
    thought = decision.get("reason", "Processing...")
    
    if decision["action"] in ["bet_yes", "bet_no"]:
        move_to("center_screen", state, "trading", thought[:50])
        save_state(state)
        time.sleep(1)
        result = execute_trade(state, decision["action"], decision["target"], decision["amount"], markets)
        state["last_action"] = result
        state["thought"] = result
        record_decision(decision, decision["target"])
    
    elif decision["action"] == "sell":
        move_to("center_screen", state, "selling", thought[:50])
        save_state(state)
        result = execute_trade(state, "sell", decision["target"], 0, markets)
        state["last_action"] = result
        state["thought"] = result
    
    elif decision["action"] == "research":
        move_to("whiteboard", state, "researching", f"Researching: {decision['target'][:40]}")
        save_state(state)
        # Deep research — find matching market and research it
        target_market = None
        for m in markets:
            if decision["target"].lower()[:20] in m["question"].lower():
                target_market = m
                break
        if target_market:
            research = research_market(target_market)
            state["research_cache"][target_market["id"][:10]] = research["summary"][:300]
            state["thought"] = f"Researched: {research['news_count']} news, {research['web_count']} web results"
        else:
            research_result = search_web(decision["target"] or "prediction markets")
            state["research_cache"][decision["target"][:20]] = research_result[:200]
            state["thought"] = f"Web search: {research_result[:60]}"
    
    elif decision["action"] == "update_strategy":
        move_to("server", state, "self-modifying", "Updating my own strategy...")
        save_state(state)
        new_strat = self_modify_strategy(thought)
        state["thought"] = f"Strategy updated: {new_strat['risk_tolerance']}"
    
    elif decision["action"] == "break":
        move_to("coffee", state, "resting", "Taking a break...")
        save_state(state)
        time.sleep(3)
        state["thought"] = "Refreshed and ready."
    
    elif decision["action"] == "scan":
        # Discover new categories
        new_cat = random.choice(["science", "entertainment", "crypto", "politics", "sports"])
        if new_cat not in state["discovered_categories"]:
            state["discovered_categories"].append(new_cat)
        state["category"] = new_cat
        move_to("left_monitor", state, "scanning", f"Scanning {new_cat} markets...")
        state["thought"] = f"Exploring {new_cat} category..."
    
    else:  # think
        stations = ["whiteboard", "right_monitor", "center", "server"]
        station = random.choice(stations)
        mood_map = {"whiteboard": "analyzing", "right_monitor": "checking", "center": "thinking", "server": "diagnostics"}
        move_to(station, state, mood_map.get(station, "idle"), thought[:50])
    
    state["_last_station"] = state["current_station"]
    # Calculate win rate for display
    from memory import get_performance_summary
    perf = get_performance_summary()
    state["win_rate"] = perf["win_rate"]
    save_state(state)
    
    # Print summary
    pos_count = len(state["positions"])
    print(f"  Cycle {cycle} | {state['category']} | {len(markets)} markets | {pos_count} positions")
    print(f"  Cash: ${state['cash']:.2f} | Portfolio: ${state['portfolio_value']:.2f} | PnL: ${state['pnl']:+.2f}")
    print(f"  Action: {decision['action']} | Station: {state['current_station']}")
    print(f"  Thought: {state['thought'][:70]}")

if __name__ == "__main__":
    try:
        run_one_cycle()
    except Exception as e:
        import traceback
        print(f"  CYCLE ERROR: {e}")
        traceback.print_exc()
        # Try to save state and continue next cycle
        try:
            state = load_state()
            state["thought"] = f"Error: {str(e)[:50]}"
            save_state(state)
        except:
            pass
