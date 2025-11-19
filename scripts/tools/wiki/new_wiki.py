import requests

def wikipedia_search_images(query="Marie Curie", lang="en", limit=5):
    """
    Searches Wikipedia for a query and returns the title, description,
    and thumbnail URL for the top results.

    The Core REST API is used for efficiency, and a proper User-Agent
    is included to comply with Wikimedia's policy.
    """
    base_url = f"https://api.wikimedia.org/core/v1/wikipedia/{lang}/"
    endpoint = f"search/page?q={query}&limit={limit}"
    url = base_url + endpoint

    # 🚨 Crucial Fix: Include a descriptive User-Agent header
    # Wikimedia policy requires a descriptive User-Agent header 
    # to avoid being blocked (HTTP 403) or rate-limited.
    headers = {
        'User-Agent': 'MyImageFinderApp/1.0 (https://example.com/myapp; myname@example.org)',
    }

    try:
        response = requests.get(url, headers=headers)
        
        # 1. Check for HTTP errors (like 403 Forbidden) before decoding
        response.raise_for_status() 

        data = response.json()
        
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error occurred: {e}")
        # Print the response text to see the error message from the server
        print(f"Server response (not JSON): {response.text}") 
        return []
    except requests.exceptions.JSONDecodeError as e:
        print(f"JSON Decode Error: {e}")
        print(f"Raw response text (failed to decode): {response.text}")
        return []

    results = []
    for page in data.get('pages', []):
        # The Core API returns thumbnail info directly
        thumbnail_url = page.get('thumbnail', {}).get('url')
        
        results.append({
            "title": page.get('title'),
            "description": page.get('description'),
            "url": 'https:' + thumbnail_url if thumbnail_url else None
        })
        
    return results

# Example
if __name__ == "__main__":
    imgs = wikipedia_search_images("Dodo bird", limit=3)
    print(f"Found {len(imgs)} image results")
    for img in imgs:
        print(img)