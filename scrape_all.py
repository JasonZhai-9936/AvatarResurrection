"""
compare_searches.py

Runs 3 different search approaches for a hard-coded query:
 - DuckDuckGo (ddgs / duckduckgo-search)
 - Google Programmable Search Engine (Custom Search JSON API) -- requires GOOGLE_API_KEY in env
 - Playwright scraping of an actual Google search results page

Prints and returns structured results for simple side-by-side comparison.
"""

import os
import sys
import json
import time
import requests
import urllib.parse

# --- DuckDuckGo import fallback (package renamed) ---
try:
    # old import used by many examples
    from duckduckgo_search import DDGS  # type: ignore
except Exception:
    try:
        # new package name
        from ddgs import DDGS  # type: ignore
    except Exception:
        DDGS = None

# --- Playwright import ---
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

QUERY = "cowboys playoff chances"
MAX_RESULTS = 5

def search_duckduckgo(query, max_results=MAX_RESULTS):
    print("\n=== DUCKDUCKGO RESULTS ===")
    if DDGS is None:
        print("[DUCKDUCKGO] ddgs / duckduckgo_search package not installed or import failed.")
        print("Install: pip install ddgs")
        return None

    try:
        results = []
        # DDGS() supports a context manager in both packages
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                # ddgs.text returns dict-like objects; convert to normal dict
                item = {
                    "title": r.get("title"),
                    "href": r.get("href"),
                    "body": r.get("body") or r.get("snippet") or ""
                }
                results.append(item)
        for i, r in enumerate(results):
            print(f"[{i}] {r['title']} — {r['href']}")
        return results
    except Exception as e:
        print("[DUCKDUCKGO] Error:", e)
        return None

def search_google_cse(query, cx, max_results=MAX_RESULTS):
    print("\n=== GOOGLE PROGRAMMABLE SEARCH ENGINE (CSE) RESULTS ===")
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("[GOOGLE CSE] GOOGLE_API_KEY environment variable not set. Skipping CSE test.")
        print("Set it with: export GOOGLE_API_KEY='YOUR_KEY' (or set in OS environment)")
        return None

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": max_results
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        results = []
        for it in items[:max_results]:
            results.append({
                "title": it.get("title"),
                "link": it.get("link"),
                "snippet": it.get("snippet")
            })
        if not results:
            print("[GOOGLE CSE] No items returned. Check API key, CX, or quota.")
        else:
            for i, r in enumerate(results):
                print(f"[{i}] {r['title']} — {r['link']}")
        return results
    except requests.HTTPError as he:
        print("[GOOGLE CSE] HTTP error:", he, "Response:", getattr(he, "response", None))
        try:
            print("Raw response:", resp.text)
        except:
            pass
        return None
    except Exception as e:
        print("[GOOGLE CSE] Error:", e)
        return None

def search_playwright_google(query, max_results=MAX_RESULTS, timeout_ms=20000):
    print("\n=== PLAYWRIGHT GOOGLE SCRAPE RESULTS ===")
    if sync_playwright is None:
        print("[PLAYWRIGHT] Playwright not installed. Install with: pip install playwright ; playwright install chromium")
        return None

    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/search?q={encoded}&hl=en"

    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            # Navigate directly to search URL to avoid having to click/type into the search box
            page.goto(url, timeout=timeout_ms)
            # Try to handle consent popups by clicking common accept buttons (if present)
            try:
                # multiple common button texts
                for txt in ("I agree", "I accept", "Accept all", "Accept"):
                    try:
                        page.locator(f"button:has-text('{txt}')").click(timeout=1500)
                        time.sleep(0.5)
                        break
                    except:
                        pass
            except Exception:
                pass

            # Wait for search results container; try a few selectors
            try:
                page.wait_for_selector("div#search", timeout=timeout_ms)
                container = page.locator("div#search")
            except Exception:
                # fallback selectors
                try:
                    page.wait_for_selector("div.g", timeout=timeout_ms)
                    container = page.locator("div.g")
                except Exception as e:
                    print("[PLAYWRIGHT] Could not find search results container:", e)
                    browser.close()
                    return None

            # Extract top result blocks
            # Prefer extracting titles (h3) and the parent anchor href
            blocks = page.locator("div#search .g, div.g").all()  # list-like locator
            # If above produced nothing, try selecting h3 elements directly
            if not blocks:
                titles = page.locator("h3").all_text_contents()
                links = page.locator("a").evaluate_all("els => els.map(e => e.href)")
                for i in range(min(max_results, len(titles))):
                    results.append({"title": titles[i], "link": links[i]})
            else:
                # iterate through blocks and extract h3 + anchor
                count = 0
                for i in range(len(blocks)):
                    if count >= max_results:
                        break
                    try:
                        block = blocks[i]
                        title = block.locator("h3").inner_text(timeout=2000)
                        # find ancestor link
                        # sometimes the <a> is a parent of h3 or sibling; find first anchor with href inside block
                        try:
                            link = block.locator("a").first.get_attribute("href")
                        except Exception:
                            # fallback: evaluate JS to find first anchor inside block
                            link = block.evaluate("b => (b.querySelector('a') && b.querySelector('a').href) || ''")
                        if title:
                            results.append({"title": title, "link": link})
                            count += 1
                    except Exception:
                        continue

            # final fallback if no results
            if not results:
                # try grabbing h3s and nearby anchors globally
                titles = page.locator("h3").all_text_contents()
                links = page.locator("a").evaluate_all("els => els.map(e => e.href)")
                for i in range(min(max_results, len(titles))):
                    results.append({"title": titles[i], "link": links[i] if i < len(links) else ""})

            browser.close()
    except Exception as e:
        print("[PLAYWRIGHT] Error during scraping:", e)
        return None

    if results:
        for i, r in enumerate(results[:max_results]):
            print(f"[{i}] {r.get('title')} — {r.get('link')}")
    else:
        print("[PLAYWRIGHT] No results found or scraping failed.")
    return results

def main():
    print(f"\nRunning search tests for query: '{QUERY}'\n")

    ddg = search_duckduckgo(QUERY)
    # Google CSE: read CX from environment or hardcode your CX
    CX = os.environ.get("GOOGLE_CSE_CX", "532ce8b2629f54f5d")  # replace with your CX or set env var
    gcs = search_google_cse(QUERY, CX)
    pw = search_playwright_google(QUERY)

    consolidated = {
        "query": QUERY,
        "duckduckgo": ddg,
        "google_cse": gcs,
        "playwright_google": pw
    }

    # Save to JSON for easier programmatic comparison
    outfile = "search_comparison_results.json"
    try:
        with open(outfile, "w", encoding="utf-8") as f:
            json.dump(consolidated, f, indent=2, ensure_ascii=False)
        print(f"\nSaved consolidated results to: {outfile}")
    except Exception as e:
        print("Could not save results:", e)

if __name__ == "__main__":
    main()
