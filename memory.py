"""Agent memory — tracks decisions, outcomes, and learns from patterns."""
import json
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent / "data"
MEMORY_FILE = DATA_DIR / "memory.json"
STRATEGY_FILE = DATA_DIR / "strategy.json"

def load_memory():
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text())
    return {"decisions": [], "wins": 0, "losses": 0, "total_pnl": 0, "patterns": {}, "learnings": []}

def save_memory(mem):
    MEMORY_FILE.write_text(json.dumps(mem, indent=2))

def load_strategy():
    if STRATEGY_FILE.exists():
        return json.loads(STRATEGY_FILE.read_text())
    return {
        "min_yes_price": 0.15,
        "max_yes_price": 0.45,
        "min_volume": 5000,
        "max_bet_pct": 0.20,
        "preferred_categories": ["crypto", "politics", "sports", "science"],
        "risk_tolerance": "moderate",
        "research_before_bet": True,
        "notes": "Starting strategy — will be updated by agent based on performance",
    }

def save_strategy(strat):
    STRATEGY_FILE.write_text(json.dumps(strat, indent=2))

def record_decision(decision, market_question, result=None):
    """Record a decision and optionally its outcome."""
    mem = load_memory()
    entry = {
        "time": datetime.now().isoformat(),
        "action": decision.get("action", "skip"),
        "market": market_question[:80],
        "amount": decision.get("amount", 0),
        "confidence": decision.get("confidence", "LOW"),
        "reason": decision.get("reason", ""),
        "category": decision.get("category", ""),
        "result": result,  # None = pending, "win", "loss", or PnL amount
    }
    mem["decisions"].append(entry)
    # Keep last 50 decisions
    if len(mem["decisions"]) > 50:
        mem["decisions"] = mem["decisions"][-50:]
    save_memory(mem)
    return entry

def record_outcome(index, pnl, won):
    """Record the outcome of a past decision."""
    mem = load_memory()
    if 0 <= index < len(mem["decisions"]):
        mem["decisions"][index]["result"] = f"{'win' if won else 'loss'}: ${pnl:+.2f}"
        if won:
            mem["wins"] += 1
        else:
            mem["losses"] += 1
        mem["total_pnl"] += pnl
        # Learn from patterns
        cat = mem["decisions"][index].get("category", "")
        if cat:
            if cat not in mem["patterns"]:
                mem["patterns"][cat] = {"wins": 0, "losses": 0}
            if won:
                mem["patterns"][cat]["wins"] += 1
            else:
                mem["patterns"][cat]["losses"] += 1
        save_memory(mem)

def get_performance_summary():
    """Get a summary of past performance."""
    mem = load_memory()
    total = mem["wins"] + mem["losses"]
    win_rate = (mem["wins"] / total * 100) if total > 0 else 0
    return {
        "total_decisions": len(mem["decisions"]),
        "wins": mem["wins"],
        "losses": mem["losses"],
        "win_rate": f"{win_rate:.1f}%",
        "total_pnl": f"${mem['total_pnl']:+.2f}",
        "patterns": mem["patterns"],
        "recent_decisions": mem["decisions"][-5:],
        "learnings": mem["learnings"][-10:],
    }

def add_learning(learning):
    """Add a learning from experience."""
    mem = load_memory()
    mem["learnings"].append({
        "time": datetime.now().isoformat(),
        "insight": learning,
    })
    if len(mem["learnings"]) > 20:
        mem["learnings"] = mem["learnings"][-20:]
    save_memory(mem)

def self_modify_strategy(reason):
    """Let the agent update its own strategy based on performance."""
    strat = load_strategy()
    perf = get_performance_summary()
    
    # Adjust based on win rate
    wins = perf["wins"]
    losses = perf["losses"]
    total = wins + losses
    
    if total >= 5:
        win_rate = wins / total
        if win_rate < 0.3:
            # Doing poorly — be more conservative
            strat["max_bet_pct"] = max(0.05, strat["max_bet_pct"] - 0.03)
            strat["min_volume"] = min(20000, strat["min_volume"] + 2000)
            strat["risk_tolerance"] = "conservative"
            add_learning(f"Win rate {win_rate:.0%} — becoming more conservative. Max bet: {strat['max_bet_pct']:.0%}")
        elif win_rate > 0.6:
            # Doing well — can be slightly more aggressive
            strat["max_bet_pct"] = min(0.30, strat["max_bet_pct"] + 0.02)
            strat["risk_tolerance"] = "aggressive"
            add_learning(f"Win rate {win_rate:.0%} — increasing aggression. Max bet: {strat['max_bet_pct']:.0%}")
    
    strat["notes"] = reason
    save_strategy(strat)
    return strat

if __name__ == "__main__":
    print(json.dumps(get_performance_summary(), indent=2))
