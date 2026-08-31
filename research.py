"""Web research tools for the agent — scrapes Polymarket and news."""
import httpx
import json
import re
from datetime import datetime

def scrape_polymarket_event(url_or_slug):
    """Scrape a Polymarket event page for details."""
    try:
        if not url_or_slug.startswith("http"):
            url = f"https://polymarket.com/event/{url_or_slug}"
        else:
            url = url_or_slug
        r = httpx.get(url, timeout=10, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)"
        })
        # Extract useful text
        text = r.text
        # Remove script/style tags
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:2000]
    except Exception as e:
        return f"Error scraping: {e}"

def search_news(query, num_results=3):
    """Search for news using DuckDuckGo lite (no API key needed)."""
    try:
        r = httpx.get("https://lite.duckduckgo.com/lite/", params={"q": query}, timeout=10, headers={
            "User-Agent": "Mozilla/5.0"
        })
        # Extract result links and snippets
        results = []
        # Find result links
        links = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*class="result-link"[^>]*>([^<]+)</a>', r.text)
        snippets = re.findall(r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>', r.text, re.DOTALL)
        
        for i, (url, title) in enumerate(links[:num_results]):
            snippet = snippets[i].strip() if i < len(snippets) else ""
            snippet = re.sub(r'<[^>]+>', '', snippet).strip()
            results.append({"title": title.strip(), "url": url, "snippet": snippet[:200]})
        return results
    except Exception as e:
        return [{"title": "Search error", "url": "", "snippet": str(e)}]

def get_market_details(market_id):
    """Get detailed info about a specific Polymarket market."""
    try:
        r = httpx.get(f"https://gamma-api.polymarket.com/markets/{market_id}", timeout=10)
        data = r.json()
        return {
            "question": data.get("question", ""),
            "description": data.get("description", "")[:500],
            "volume": float(data.get("volume", 0)),
            "liquidity": float(data.get("liquidityClob", 0)),
            "end_date": data.get("endDate", ""),
            "outcomes": json.loads(data.get("outcomes", "[]")),
            "prices": json.loads(data.get("outcomePrices", "[]")),
        }
    except Exception as e:
        return {"error": str(e)}

def web_search_and_summarize(query):
    """Search the web and return a summary for the agent."""
    results = search_news(query, 3)
    summary = f"Search results for '{query}':\n"
    for i, r in enumerate(results):
        summary += f"{i+1}. {r['title']}\n   {r['snippet']}\n"
    return summary

if __name__ == "__main__":
    print("=== Testing research tools ===")
    print("\nNews search:")
    print(web_search_and_summarize("bitcoin prediction 2026"))
    print("\nMarket details:")
    details = get_market_details("test")
    print(json.dumps(details, indent=2))
