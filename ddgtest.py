import sys
from ddgs import DDGS # Using the new package name directly

def run_standalone_search(query: str, max_results: int = 15):
    print(f"--- Starting Search: {query} ---")
    
    # We use a custom user agent and explicit region to force English/Global results
    # and avoid the local/Chinese results you were getting.
    try:
        with DDGS() as ddgs:
            # region='wt-wt' is 'no region' (global)
            # backend='api' is often more consistent for specific queries
            search_gen = ddgs.text(
                query, 
                region='wt-wt', 
                safesearch='moderate', 
                timelimit=None, 
                max_results=max_results
            )
            
            results = list(search_gen)
            
            if not results:
                print("No results found.")
                return

            for i, r in enumerate(results, 1):
                print(f"\n{'='*60}")
                print(f"RESULT #{i}")
                print(f"TITLE: {r.get('title')}")
                print(f"URL:   {r.get('href')}")
                print(f"BODY:\n{r.get('body') or r.get('snippet')}")
                print(f"{'='*60}\n")

    except Exception as e:
        print(f"[ERROR] Search failed: {e}")

if __name__ == "__main__":
    search_query = "Mickey Mantle June 21 1960"
    if len(sys.argv) > 1:
        search_query = " ".join(sys.argv[1:])
    run_standalone_search(search_query)