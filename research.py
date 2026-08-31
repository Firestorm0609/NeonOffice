"""Social research tools — aggregates free data sources for the agent."""
import httpx
import json
import re
from datetime import datetime


# ═══════════════════════════════════════════
#  GOOGLE NEWS RSS — real-time news
# ═══════════════════════════════════════════
def google_news(query, limit=5):
    """Search Google News via RSS. Free, no API key."""
    try:
        r = httpx.get("https://news.google.com/rss/search", params={
            "q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"
        }, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        titles = re.findall(r'<title>(.*?)</title>', r.text)[1:]  # skip feed title
        links = re.findall(r'<link/>(.*?)<pubDate', r.text, re.DOTALL)
        results = []
        for i, title in enumerate(titles[:limit]):
            link = links[i].strip() if i < len(links) else ""
            results.append({"title": title.strip(), "source": "Google News", "url": link})
        return results
    except Exception as e:
        return [{"title": f"Error: {e}", "source": "Google News"}]


# ═══════════════════════════════════════════
#  DUCKDUCKGO — general web search
# ═══════════════════════════════════════════
def duckduckgo(query, limit=5):
    """Search DuckDuckGo. Free, no API key."""
    try:
        r = httpx.get("https://lite.duckduckgo.com/lite/", params={"q": query},
                       timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        links = re.findall(r'<a[^>]+rel="nofollow"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>', r.text)
        results = []
        for url, title in links[:limit]:
            # Clean up DuckDuckGo redirect URLs
            if "uddg=" in url:
                import urllib.parse
                url = urllib.parse.unquote(url.split("uddg=")[1].split("&")[0])
            results.append({"title": title.strip(), "source": "Web", "url": url})
        return results
    except Exception as e:
        return [{"title": f"Error: {e}", "source": "Web"}]


# ═══════════════════════════════════════════
#  COINGECKO — crypto trending & social
# ═══════════════════════════════════════════
def coingecko_trending():
    """Get trending coins from CoinGecko. Free, no API key."""
    try:
        r = httpx.get("https://api.coingecko.com/api/v3/search/trending", timeout=8)
        if r.status_code == 200:
            coins = r.json().get("coins", [])
            return [{"name": c["item"]["name"], "symbol": c["item"]["symbol"],
                     "rank": c["item"].get("market_cap_rank", "?"),
                     "price_btc": c["item"].get("price_btc", 0)}
                    for c in coins[:10]]
    except:
        pass
    return []


# ═══════════════════════════════════════════
#  POLYMARKET — market descriptions
# ═══════════════════════════════════════════
def polymarket_description(market_id):
    """Get detailed description of a Polymarket market."""
    try:
        r = httpx.get(f"https://gamma-api.polymarket.com/markets/{market_id}", timeout=8)
        data = r.json()
        return {
            "question": data.get("question", ""),
            "description": data.get("description", "")[:500],
            "volume": float(data.get("volume", 0)),
            "liquidity": float(data.get("liquidityClob", 0)),
        }
    except:
        return {}


# ═══════════════════════════════════════════
#  FXTWITTER — individual tweet data
# ═══════════════════════════════════════════
def get_tweet(tweet_id):
    """Fetch a specific tweet via fxtwitter API. Free, no auth."""
    try:
        r = httpx.get(f"https://api.fxtwitter.com/status/{tweet_id}", timeout=8)
        if r.status_code == 200:
            data = r.json().get("tweet", {})
            return {
                "author": data.get("author", {}).get("name", ""),
                "text": data.get("text", ""),
                "likes": data.get("likes", 0),
                "retweets": data.get("retweets", 0),
                "date": data.get("created_at", ""),
            }
    except:
        pass
    return {}


# ═══════════════════════════════════════════
#  COMBINED RESEARCH — the main function
# ═══════════════════════════════════════════
def research_topic(topic, market_description=""):
    """Full research on a topic — combines all sources."""
    results = {
        "topic": topic,
        "news": [],
        "web": [],
        "trending": [],
        "timestamp": datetime.now().isoformat(),
    }
    
    # Google News
    results["news"] = google_news(topic, 3)
    
    # DuckDuckGo
    results["web"] = duckduckgo(topic, 3)
    
    # CoinGecko trending (if crypto-related)
    crypto_keywords = ["bitcoin", "ethereum", "solana", "crypto", "token", "defi", "nft"]
    if any(kw in topic.lower() for kw in crypto_keywords):
        results["trending"] = coingecko_trending()
    
    # Polymarket description
    if market_description:
        results["description"] = market_description[:300]
    
    # Build summary for LLM
    summary = f"Research on: {topic}\n\n"
    if results["news"]:
        summary += "NEWS:\n"
        for n in results["news"][:3]:
            summary += f"  - {n['title']}\n"
    if results["web"]:
        summary += "\nWEB:\n"
        for w in results["web"][:3]:
            summary += f"  - {w['title']}\n"
    if results["trending"]:
        summary += "\nTRENDING CRYPTO:\n"
        for t in results["trending"][:5]:
            summary += f"  - {t['name']} ({t['symbol']}) rank #{t['rank']}\n"
    if market_description:
        summary += f"\nMARKET INFO:\n  {market_description[:200]}\n"
    
    results["summary"] = summary
    return results


def web_search_and_summarize(query):
    """Quick search and summary for the agent."""
    news = google_news(query, 2)
    web = duckduckgo(query, 2)
    summary = f"Results for '{query}':\n"
    for n in news:
        summary += f"  NEWS: {n['title']}\n"
    for w in web:
        summary += f"  WEB: {w['title']}\n"
    return summary


if __name__ == "__main__":
    print("=== Full Research Test ===")
    result = research_topic("bitcoin prediction market 2026")
    print(result["summary"])
