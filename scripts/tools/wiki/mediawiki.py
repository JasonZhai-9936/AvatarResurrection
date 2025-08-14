import requests

def wikipedia_page_images(title="Charles Darwin"):
    base = "https://en.wikipedia.org/w/api.php"

    # Step 1: Get all image filenames used in the page
    params = {
        "action": "query",
        "titles": title,
        "prop": "images",
        "imlimit": "max",
        "format": "json"
    }
    data = requests.get(base, params=params).json()
    pages = data.get("query", {}).get("pages", {})
    filenames = []
    for page in pages.values():
        for img in page.get("images", []):
            filenames.append(img["title"])  # e.g. "File:Charles Darwin 1880.jpg"

    # Step 2: Get image URLs + metadata from Wikimedia Commons
    results = []
    if filenames:
        params = {
            "action": "query",
            "titles": "|".join(filenames),
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "format": "json"
        }
        img_data = requests.get(base, params=params).json()
        for page in img_data.get("query", {}).get("pages", {}).values():
            if "imageinfo" in page:
                info = page["imageinfo"][0]
                results.append({
                    "file": page["title"],
                    "url": info["url"],
                    "description": info.get("extmetadata", {}).get("ImageDescription", {}).get("value"),
                    "license": info.get("extmetadata", {}).get("LicenseShortName", {}).get("value")
                })
    return results

# Example
for img in wikipedia_page_images("Dorothy Hodgkin"):
    print(img)
