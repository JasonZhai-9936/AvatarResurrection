# ddg_scrape.py - DuckDuckGo Search Tool for Darwin Chatbot
"""
Exposes a function run_ddg_search(query, max_results) that returns
a list of dictionaries containing title, href, and body/snippet.
"""

import time
import sys

# Try imports (support both package names)
DDGS = None
try:
    from ddgs import DDGS  # new package name
    DDGS = DDGS
except Exception:
    try:
        from duckduckgo_search import DDGS as DDGS_old  # older package name
        DDGS = DDGS_old
    except Exception:
        DDGS = None

def run_ddg_search(query: str, max_results: int = 15):
    """
    Searches DuckDuckGo and returns a list of dictionaries.
    Each dict has: 'title', 'href', 'body'
    """
    if DDGS is None:
        print("[DDG] Error: DuckDuckGo search library not found.")
        return []

    results = []
    print(f"[DDG] Searching for: {query!r} (max={max_results})")
    
    try:
        with DDGS() as ddgs:
            # Fetch results
            # Note: The library API changes frequently. 
            # .text() is the common method for text search.
            search_gen = ddgs.text(query, max_results=max_results)
            
            for r in search_gen:
                item = {
                    "title": r.get("title", "No Title"),
                    "href": r.get("href", "#"),
                    "body": r.get("body") or r.get("snippet") or ""
                }
                results.append(item)
                
    except Exception as e:
        print(f"[DDG] Error during search: {e}")
        return []

    print(f"[DDG] Retrieved {len(results)} results.")
    return results

if __name__ == "__main__":
    # Test block
    q = "Who won the most recent Super Bowl?"
    res = run_ddg_search(q, 5)
    for i, r in enumerate(res):
        print(f"{i+1}. {r['title']} - {r['href']}")