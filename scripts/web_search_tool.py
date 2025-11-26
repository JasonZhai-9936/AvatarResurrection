# web_search_tool.py - DuckDuckGo Search Wrapper
from colorama import Fore, Style
import time

# Try imports (support both package names)
DDGS = None
try:
    from ddgs import DDGS
except Exception:
    try:
        from duckduckgo_search import DDGS
    except Exception:
        DDGS = None

class WebSearchTool:
    def __init__(self):
        if DDGS is None:
            print(f"{Fore.RED}[SEARCH] Warning: 'ddgs' or 'duckduckgo_search' not installed.{Style.RESET_ALL}")
            self.available = False
        else:
            self.available = True

    def search(self, query: str, max_results: int = 15):
        """
        Searches DuckDuckGo and returns a formatted string for the LLM.
        Returns: String containing analysis of Title, URL, and Snippets.
        """
        if not self.available:
            return "Search functionality is unavailable (library missing)."

        print(f"{Fore.MAGENTA}[SEARCH] Querying DuckDuckGo: '{query}' (Max {max_results})...{Style.RESET_ALL}")
        
        results = []
        try:
            with DDGS() as ddgs:
                # Use the generator to fetch results
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", "No Title"),
                        "href": r.get("href", "#"),
                        "body": r.get("body") or r.get("snippet") or "No details available."
                    })
        except Exception as e:
            print(f"{Fore.RED}[SEARCH] Error: {e}{Style.RESET_ALL}")
            return f"Error performing search: {e}"

        if not results:
            return "No search results found."

        # Format for LLM consumption
        formatted_output = f"Search Results for '{query}':\n\n"
        for i, r in enumerate(results, 1):
            formatted_output += (
                f"Result {i}:\n"
                f"Title: {r['title']}\n"
                f"URL: {r['href']}\n"
                f"Summary: {r['body']}\n"
                f"{'-'*40}\n"
            )
        
        print(f"{Fore.MAGENTA}[SEARCH] Retrieved {len(results)} results.{Style.RESET_ALL}")
        return formatted_output