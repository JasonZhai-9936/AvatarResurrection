#vary wild and random images, dont use this api

import requests

def commons_category_images(category="Charles Darwin"):
    base = "https://commons.wikimedia.org/w/api.php"

    # Step 1: Get all files in the category
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": f"Category:{category}",
        "cmtype": "file",
        "cmlimit": "max",
        "format": "json"
    }

    files = []
    while True:
        data = requests.get(base, params=params).json()
        files.extend(f["title"] for f in data.get("query", {}).get("categorymembers", []))
        if "continue" in data:
            params.update(data["continue"])
        else:
            break

    # Step 2: Batch requests to avoid URL length limit
    results = []
    batch_size = 20  # safe batch size
    for i in range(0, len(files), batch_size):
        batch = files[i:i+batch_size]
        params2 = {
            "action": "query",
            "titles": "|".join(batch),
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "format": "json"
        }
        img_data = requests.get(base, params=params2).json()
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
if __name__ == "__main__":
    imgs = commons_category_images("Charles Darwin")
    print(f"Found {len(imgs)} images")
    for img in imgs[:5]:
        print(img)
