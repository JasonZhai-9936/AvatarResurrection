#!/usr/bin/env python3
"""
ddg_search_llm.py

DuckDuckGo search results printer for LLM-friendly consumption.

- Uses `ddgs` (preferred) or `duckduckgo_search` (older name) if available.
- Prints results in a structured format suitable for LLM summarization.

Example:
    python ddg_search_llm.py --query "cowboys playoff chances" --max 25
"""

import argparse
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

def run_ddg_search(query: str, max_results: int):
    if DDGS is None:
        raise RuntimeError(
            "DuckDuckGo search library not available. Install with:\n"
            "  pip install ddgs\n"
            "or\n"
            "  pip install duckduckgo-search"
        )

    results = []
    print(f"[DDG] Searching for: {query!r}  (max={max_results})\n")
    start = time.time()
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                item = {
                    "title": r.get("title"),
                    "href": r.get("href"),
                    "body": r.get("body") or r.get("snippet") or ""
                }
                results.append(item)
    except Exception as e:
        raise RuntimeError(f"Error while running DDG search: {e}") from e

    elapsed = time.time() - start
    print(f"[DDG] Retrieved {len(results)} results in {elapsed:.2f}s\n")
    return results

def main():
    parser = argparse.ArgumentParser(description="DuckDuckGo search printer for LLMs.")
    parser.add_argument("--query", "-q", type=str, default="when did darwin die?", help="Search query")
    parser.add_argument("--max", "-m", type=int, default=25, help="Max results to fetch")
    args = parser.parse_args()

    try:
        results = run_ddg_search(args.query, args.max)
    except RuntimeError as e:
        print("ERROR:", e)
        sys.exit(2)

    print("=== DUCKDUCKGO SEARCH RESULTS ===\n")
    for i, r in enumerate(results, 1):
        print(f"Result #{i}:")
        print(f"Title: {r['title']}")
        print(f"URL: {r['href']}")
        print(f"Snippet: {r['body']}\n")
        print("-" * 80)

if __name__ == "__main__":
    main()
