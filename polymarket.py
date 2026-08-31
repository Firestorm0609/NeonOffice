"""Polymarket API client — read-only, no auth needed for paper trading."""
import httpx
import json
from datetime import datetime

GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"

def get_markets(limit=20, tag=None, min_volume=1000):
    """Fetch active prediction markets."""
    params = {
        "limit": limit,
        "active": True,
        "closed": False,
        "order": "volume24hr",
        "ascending": False,
    }
    if tag:
        params["tag"] = tag
    try:
        r = httpx.get(f"{GAMMA_API}/markets", params=params, timeout=10)
        markets = r.json()
        results = []
        for m in markets:
            vol = float(m.get("volume24hr", 0))
            if vol < min_volume:
                continue
            prices = json.loads(m.get("outcomePrices", "[]"))
            yes_price = float(prices[0]) if prices else 0
            no_price = float(prices[1]) if len(prices) > 1 else 0
            results.append({
                "id": m.get("id"),
                "question": m.get("question", ""),
                "slug": m.get("slug", ""),
                "yes_price": yes_price,
                "no_price": no_price,
                "volume_24h": vol,
                "liquidity": float(m.get("liquidityClob", 0)),
                "end_date": m.get("endDate", ""),
                "category": m.get("groupSlug", ""),
                "token_yes": m.get("clobTokenIds", ["", ""])[0] if m.get("clobTokenIds") else "",
                "token_no": m.get("clobTokenIds", ["", ""])[1] if m.get("clobTokenIds") and len(m.get("clobTokenIds", [])) > 1 else "",
                "description": m.get("description", "")[:200],
            })
        return results
    except Exception as e:
        print(f"  Polymarket API error: {e}")
        return []

def get_trending(limit=10):
    """Get highest volume markets."""
    return get_markets(limit=limit, min_volume=5000)

def get_crypto_markets():
    """Get crypto-related prediction markets."""
    return get_markets(limit=30, tag="crypto", min_volume=1000)

def get_politics_markets():
    """Get politics prediction markets."""
    return get_markets(limit=30, tag="politics", min_volume=1000)

def search_markets(query, limit=5):
    """Search markets by keyword."""
    try:
        r = httpx.get(f"{GAMMA_API}/markets", params={
            "limit": limit, "active": True, "closed": False,
        }, timeout=10)
        markets = r.json()
        query_lower = query.lower()
        return [
            {
                "id": m.get("id"),
                "question": m.get("question", ""),
                "yes_price": float(json.loads(m.get("outcomePrices", "[]"))[0]) if json.loads(m.get("outcomePrices", "[]")) else 0,
                "no_price": float(json.loads(m.get("outcomePrices", "[]"))[1]) if len(json.loads(m.get("outcomePrices", "[]"))) > 1 else 0,
                "volume_24h": float(m.get("volume24hr", 0)),
            }
            for m in markets
            if query_lower in m.get("question", "").lower()
        ]
    except:
        return []

def get_market_by_id(market_id):
    """Get a specific market by ID."""
    try:
        r = httpx.get(f"{GAMMA_API}/markets/{market_id}", timeout=10)
        return r.json()
    except:
        return None

if __name__ == "__main__":
    print("=== Trending Markets ===")
    for m in get_trending(5):
        print(f"  {m['question'][:60]}")
        print(f"    YES: ${m['yes_price']:.3f} | NO: ${m['no_price']:.3f} | Vol: ${m['volume_24h']:,.0f}")
