"""
NeonOffice — Autonomous Trading Agent

The agent lives in a visual room and performs real tasks:
- Scans prices (walks to left monitor)
- Analyzes markets (walks to whiteboard)
- Executes trades (walks to center screen)
- Checks portfolio (walks to right monitor)
- Rests (walks to coffee)

User just funds the wallet. Agent does everything else.
"""
import json
import time
import random
from datetime import datetime
from pathlib import Path
from openai import OpenAI
import httpx

# ============================================================
# Config
# ============================================================

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

STATE_FILE = DATA_DIR / "agent_state.json"
TRADES_FILE = DATA_DIR / "trades.jsonl"

# Mistral
import os
MISTRAL_KEY = os.getenv("MISTRAL_API_KEY", "")
client = OpenAI(api_key=MISTRAL_KEY, base_url="https://api.mistral.ai/v1", timeout=15.0)

# Tokens we trade
TOKENS = {
    "SOL": {"address": "So11111111111111111111111111111111111111112", "chain": "solana"},
    "WIF": {"address": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", "chain": "solana"},
    "BONK": {"address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "chain": "solana"},
    "POPCAT": {"address": "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr", "chain": "solana"},
    "TRUMP": {"address": "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN", "chain": "solana"},
    "FARTCOIN": {"address": "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump", "chain": "solana"},
}

STARTING_BALANCE = 100000.0


# ============================================================
# State
# ============================================================

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "cash": STARTING_BALANCE,
        "holdings": {},
        "total_trades": 0,
        "mood": "idle",
        "current_station": "center",
        "last_action": "none",
        "thought": "Waking up...",
        "portfolio_value": STARTING_BALANCE,
        "pnl": 0,
        "pnl_pct": 0,
    }


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def log_trade(trade):
    with open(TRADES_FILE, "a") as f:
        f.write(json.dumps(trade) + "\n")


# ============================================================
# Real API Calls
# ============================================================

def get_price(token_name):
    """Get real price from DexScreener."""
    if token_name not in TOKENS:
        return None
    info = TOKENS[token_name]
    url = f"https://api.dexscreener.com/latest/dex/tokens/{info['address']}"
    try:
        with httpx.Client(timeout=10) as http:
            resp = http.get(url)
            if resp.status_code == 200:
                data = resp.json()
                pairs = data.get("pairs", [])
                if pairs:
                    p = pairs[0]
                    return {
                        "symbol": token_name,
                        "price": float(p.get("priceUsd", "0")),
                        "change_24h": float(p.get("priceChange", {}).get("h24", "0")),
                        "volume": float(p.get("volume", {}).get("h24", 0)),
                        "liquidity": float(p.get("liquidity", {}).get("usd", 0)),
                    }
    except Exception as e:
        print(f"  Price error: {e}")
    return None


def get_all_prices():
    """Get prices for all tokens."""
    prices = {}
    for name in TOKENS:
        p = get_price(name)
        if p:
            prices[name] = p
    return prices


# ============================================================
# LLM Decision Making
# ============================================================

def ask_mistral(prompt, system="You are a crypto trading agent. Be concise."):
    """Ask Mistral for a decision."""
    try:
        response = client.chat.completions.create(
            model="mistral-small-latest",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=500,
            temperature=0.7,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        return f"Error: {e}"


def decide_action(state, prices):
    """Let Mistral decide what to do next."""
    
    # Build context
    holdings_text = "None" if not state["holdings"] else "\n".join([
        f"  {k}: {v['amount']:.4f} tokens @ ${v['price']:.6f} = ${v['value']:.2f}"
        for k, v in state["holdings"].items()
    ])
    
    prices_text = "\n".join([
        f"  {name}: ${p['price']:.6f} ({p['change_24h']:+.1f}%) Vol: ${p['volume']:,.0f}"
        for name, p in prices.items()
    ])
    
    prompt = f"""Current state:
Cash: ${state['cash']:.2f}
Portfolio value: ${state['portfolio_value']:.2f}
PnL: ${state['pnl']:.2f} ({state['pnl_pct']:+.1f}%)
Holdings:
{holdings_text}

Market prices:
{prices_text}

You are an autonomous trading agent. What should you do next?

Options:
1. SCAN — Check prices (go to left monitor)
2. ANALYZE — Think about strategy (go to whiteboard)
3. TRADE — Execute a trade (go to center screen)
4. CHECK — Review portfolio (go to right monitor)
5. REST — Take a break (go to coffee)
6. THINK — Just think (stay in center)

If you want to trade, respond with:
TRADE: BUY <TOKEN> $<AMOUNT>
or
TRADE: SELL <TOKEN> $<AMOUNT>

If you want to scan, analyze, check, rest, or think:
ACTION: <SCAN|ANALYZE|CHECK|REST|THINK>
THOUGHT: <what you're thinking>

Be decisive. Don't overthink. If the market looks good, trade."""

    response = ask_mistral(prompt)
    return response


def parse_decision(response):
    """Parse the LLM response into an action."""
    response_upper = response.upper()
    
    # Check for trade
    if "TRADE:" in response_upper:
        lines = response.split("\n")
        for line in lines:
            if "TRADE:" in line.upper():
                trade_part = line.split(":", 1)[1].strip()
                parts = trade_part.split()
                if len(parts) >= 3:
                    action = parts[0].upper()
                    token = parts[1].upper()
                    try:
                        amount = float(parts[2].replace("$", ""))
                    except:
                        amount = 0
                    return {"type": "trade", "action": action, "token": token, "amount": amount}
    
    # Check for other actions
    for action in ["SCAN", "ANALYZE", "CHECK", "REST", "THINK"]:
        if action in response_upper:
            thought = ""
            if "THOUGHT:" in response:
                thought = response.split("THOUGHT:")[1].strip()
            return {"type": action.lower(), "thought": thought}
    
    # Default
    return {"type": "scan", "thought": "Checking market..."}


# ============================================================
# Execute Actions
# ============================================================

def execute_trade(state, action, token, amount):
    """Execute a trade."""
    prices = get_all_prices()
    if token not in prices:
        return f"Token {token} not found"
    
    price = prices[token]["price"]
    
    if action == "BUY":
        if amount > state["cash"]:
            return f"Not enough cash. Have ${state['cash']:.2f}"
        
        tokens_bought = amount / price
        state["cash"] -= amount
        
        if token in state["holdings"]:
            h = state["holdings"][token]
            old_val = h["amount"] * h["price"]
            h["amount"] += tokens_bought
            h["price"] = (old_val + amount) / h["amount"]
            h["value"] = h["amount"] * h["price"]
        else:
            state["holdings"][token] = {
                "amount": tokens_bought,
                "price": price,
                "value": tokens_bought * price,
            }
        
        state["total_trades"] += 1
        
        trade = {
            "action": "BUY",
            "token": token,
            "amount_usd": amount,
            "tokens": tokens_bought,
            "price": price,
            "time": datetime.now().isoformat(),
        }
        log_trade(trade)
        return f"Bought {tokens_bought:.4f} {token} @ ${price:.6f} (${amount:.2f})"
    
    elif action == "SELL":
        if token not in state["holdings"]:
            return f"No {token} to sell"
        
        h = state["holdings"][token]
        max_sell = h["amount"] * price
        if amount > max_sell:
            amount = max_sell
        
        tokens_sold = amount / price
        state["cash"] += amount
        h["amount"] -= tokens_sold
        
        if h["amount"] <= 0.0001:
            del state["holdings"][token]
        else:
            h["value"] = h["amount"] * h["price"]
        
        state["total_trades"] += 1
        
        trade = {
            "action": "SELL",
            "token": token,
            "amount_usd": amount,
            "tokens": tokens_sold,
            "price": price,
            "time": datetime.now().isoformat(),
        }
        log_trade(trade)
        return f"Sold {tokens_sold:.4f} {token} @ ${price:.6f} (${amount:.2f})"
    
    return "Unknown action"


def update_portfolio(state, prices):
    """Update portfolio value with current prices."""
    total = state["cash"]
    for token, h in state["holdings"].items():
        if token in prices:
            h["price"] = prices[token]["price"]
            h["value"] = h["amount"] * h["price"]
        total += h.get("value", 0)
    
    state["portfolio_value"] = total
    state["pnl"] = total - STARTING_BALANCE
    state["pnl_pct"] = (state["pnl"] / STARTING_BALANCE) * 100 if STARTING_BALANCE > 0 else 0


# ============================================================
# Agent Loop
# ============================================================

def run_agent():
    """Main agent loop."""
    state = load_state()
    cycle = 0
    
    print("\n" + "="*50)
    print("NEON OFFICE — Autonomous Agent Starting")
    print("="*50 + "\n")
    
    while True:
        cycle += 1
        now = datetime.now().strftime("%H:%M:%S")
        
        print(f"\n[Cycle {cycle}] {now}")
        
        # 1. Update prices
        print("  Scanning prices...")
        state["current_station"] = "left_monitor"
        state["mood"] = "scanning"
        state["thought"] = "Checking market prices..."
        save_state(state)
        time.sleep(2)  # Visual delay
        
        prices = get_all_prices()
        update_portfolio(state, prices)
        
        for name, p in prices.items():
            print(f"    {name}: ${p['price']:.6f} ({p['change_24h']:+.1f}%)")
        
        # 2. Decide what to do
        print("  Thinking...")
        state["current_station"] = "center"
        state["mood"] = "thinking"
        state["thought"] = "Analyzing market conditions..."
        save_state(state)
        time.sleep(2)
        
        decision = decide_action(state, prices)
        print(f"  Decision: {decision[:100]}...")
        
        parsed = parse_decision(decision)
        
        # 3. Execute decision
        if parsed["type"] == "trade":
            print(f"  Trading: {parsed['action']} ${parsed['amount']:.2f} {parsed['token']}")
            state["current_station"] = "center_screen"
            state["mood"] = "trading"
            state["thought"] = f"Executing: {parsed['action']} {parsed['token']}..."
            save_state(state)
            time.sleep(3)
            
            result = execute_trade(state, parsed["action"], parsed["token"], parsed["amount"])
            print(f"  Result: {result}")
            state["last_action"] = result
            state["thought"] = result
        
        elif parsed["type"] == "scan":
            print("  Scanning prices...")
            state["current_station"] = "left_monitor"
            state["mood"] = "scanning"
            state["thought"] = parsed.get("thought", "Checking prices...")
        
        elif parsed["type"] == "analyze":
            print("  Analyzing strategy...")
            state["current_station"] = "whiteboard"
            state["mood"] = "analyzing"
            state["thought"] = parsed.get("thought", "Thinking about strategy...")
        
        elif parsed["type"] == "check":
            print("  Checking portfolio...")
            state["current_station"] = "right_monitor"
            state["mood"] = "checking"
            state["thought"] = f"Portfolio: ${state['portfolio_value']:.2f}"
        
        elif parsed["type"] == "rest":
            print("  Resting...")
            state["current_station"] = "coffee"
            state["mood"] = "resting"
            state["thought"] = "Taking a break..."
            save_state(state)
            time.sleep(10)  # Rest for 10 seconds (simulated 5 min)
        
        elif parsed["type"] == "think":
            print("  Thinking...")
            state["current_station"] = "center"
            state["mood"] = "thinking"
            state["thought"] = parsed.get("thought", "Contemplating...")
        
        # 4. Update and save
        state["last_action"] = state.get("last_action", "none")
        save_state(state)
        
        print(f"  Portfolio: ${state['portfolio_value']:.2f} (PnL: ${state['pnl']:.2f})")
        print(f"  Station: {state['current_station']}")
        print(f"  Mood: {state['mood']}")
        
        # Wait before next cycle
        wait = random.randint(15, 30)  # 15-30 seconds between cycles
        print(f"  Waiting {wait}s...")
        time.sleep(wait)


if __name__ == "__main__":
    run_agent()
