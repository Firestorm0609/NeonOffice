#!/bin/bash
# NeonOffice — Setup Script
# Run: bash setup.sh

set -e

echo "╔══════════════════════════════════════╗"
echo "║   NEON OFFICE — Prediction Market    ║"
echo "║        Autonomous Agent              ║"
echo "╚══════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found. Install it first."
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies..."
pip3 install -q httpx openai python-dotenv 2>/dev/null || pip install -q httpx openai python-dotenv

# Create .env if not exists
if [ ! -f .env ]; then
    echo ""
    echo "🔑 API Key Setup"
    echo "─────────────────────────────────────"
    echo "You need a Mistral API key (free at https://console.mistral.ai)"
    echo ""
    read -p "Enter your Mistral API key: " MISTRAL_KEY
    
    if [ -z "$MISTRAL_KEY" ]; then
        echo "❌ No key provided. You can add it later to .env"
        echo "MISTRAL_API_KEY=your_key_here" > .env
    else
        echo "MISTRAL_API_KEY=$MISTRAL_KEY" > .env
        echo "✅ Key saved to .env"
    fi
else
    echo "✅ .env already exists"
fi

# Create data directory
mkdir -p data

# Create initial state
python3 -c "
import json
state = {
    'cash': 100.0, 'positions': {}, 'total_trades': 0, 'mood': 'idle',
    'current_station': 'center', 'last_action': 'none', 'thought': 'Waking up...',
    'portfolio_value': 100.0, 'pnl': 0, 'pnl_pct': 0,
    'robot_x': 50, 'robot_y': 65, '_cycle_num': 0, '_last_station': 'center',
    'active_markets': [], 'category': 'trending', 'research_cache': {},
    'discovered_categories': ['crypto', 'politics', 'sports', 'science', 'entertainment']
}
with open('data/agent_state.json', 'w') as f:
    json.dump(state, f, indent=2)
print('✅ Initial state created')
"

# Test API key
echo ""
echo "🧪 Testing API connection..."
python3 -c "
from dotenv import load_dotenv
load_dotenv()
import os
from openai import OpenAI
key = os.getenv('MISTRAL_API_KEY', '')
if not key:
    print('⚠️  No API key found. Add MISTRAL_API_KEY to .env')
else:
    try:
        client = OpenAI(api_key=key, base_url='https://api.mistral.ai/v1', timeout=10)
        r = client.chat.completions.create(model='mistral-small-latest',
            messages=[{'role': 'user', 'content': 'Say OK'}], max_tokens=5)
        print('✅ API connection working')
    except Exception as e:
        print(f'⚠️  API error: {e}')
"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║          Setup Complete!             ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Start the agent:  python3 tick.py"
echo "Start dashboard:  python3 -m http.server 8080"
echo "Or use the tick loop: bash run_loop.sh"
