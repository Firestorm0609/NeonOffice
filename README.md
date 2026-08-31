# 🤖 NeonOffice — Autonomous Prediction Market Agent

A fully autonomous AI agent that trades on Polymarket prediction markets. The agent researches events, analyzes probabilities, and places paper trades — all visualized as a robot walking around a neon trading office.

![Dashboard](http://164.92.134.150/)

## What It Does

The agent scans prediction markets on Polymarket, researches events via Google News and DuckDuckGo, and uses Mistral AI to decide whether to bet YES or NO. Everything is visualized in real-time:

- **Left monitor** — live Polymarket markets with YES/NO percentages
- **Right monitor** — portfolio, cash, PnL, open positions
- **Whiteboard** — current strategy and research findings
- **Robot** — walks to each station as it works

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/Firestorm0609/NeonOffice.git
cd NeonOffice

# 2. Run setup (installs deps, asks for API key)
bash setup.sh

# 3. Start the agent
python3 tick.py

# 4. Start the dashboard (in another terminal)
python3 -m http.server 8080
# Open http://localhost:8080
```

## How It Works

### The Agent Loop (every 30 seconds)

1. **Scan** — Fetches live markets from Polymarket API
2. **Research** — Searches Google News + DuckDuckGo for event context
3. **Think** — Mistral AI analyzes markets and decides what to do
4. **Act** — Places paper trades, sells positions, or explores new categories
5. **Learn** — Records outcomes and updates its own strategy

### Station System

The robot walks to different stations in the office:

| Station | What It Does |
|---------|-------------|
| Left Monitor | Scans Polymarket for markets |
| Center Desk | Thinks and asks Mistral for decisions |
| Center Screen | Executes paper trades |
| Whiteboard | Researches events, writes strategy |
| Right Monitor | Reviews portfolio and positions |
| Server Rack | System health checks |
| Coffee Machine | Takes breaks |

### Research Sources (all free)

| Source | What It Provides |
|--------|-----------------|
| Polymarket API | Live market prices and descriptions |
| Google News RSS | Real-time news headlines |
| DuckDuckGo | General web search results |
| CoinGecko | Crypto trending and social sentiment |
| fxtwitter | Individual tweet data (needs tweet IDs) |

### Memory & Learning

The agent tracks:
- **Win/loss record** — how many bets it wins
- **Category patterns** — which categories it's best at
- **Past decisions** — what it decided and why
- **Self-modification** — updates its own strategy based on performance

## Configuration

### Environment Variables (.env)

```
MISTRAL_API_KEY=your_key_here
```

Get a free key at https://console.mistral.ai

### Strategy (data/strategy.json)

The agent can modify its own strategy. Default:

```json
{
  "min_yes_price": 0.15,
  "max_yes_price": 0.45,
  "min_volume": 5000,
  "max_bet_pct": 0.20,
  "risk_tolerance": "moderate"
}
```

## Files

| File | Purpose |
|------|---------|
| `tick.py` | Main agent — runs one cycle per execution |
| `polymarket.py` | Polymarket API client |
| `research.py` | Web research tools (News, DuckDuckGo, CoinGecko) |
| `memory.py` | Decision tracking and learning system |
| `index.html` | Dashboard visualization |
| `setup.sh` | One-command setup |
| `run_loop.sh` | Continuous agent loop |

## API Limits

| Source | Free Tier | Rate Limit |
|--------|-----------|-----------|
| Polymarket | Unlimited reads | No limit |
| Mistral | 1,500 req/month | 5 req/min |
| Google News | Unlimited RSS | No limit |
| DuckDuckGo | Unlimited | Soft limit |
| CoinGecko | 10-30 req/min | 50 req/hour |

## License

MIT
