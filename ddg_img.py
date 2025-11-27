import tkinter as tk
from io import BytesIO
import requests
from PIL import Image, ImageTk

# --- KEY CHANGE: Import from the new 'ddgs' package ---
from ddgs import DDGS

# ==========================================
# CONFIGURATION
# ==========================================
SEARCH_QUERY = "evolution"
MAX_RESULTS = 12
# ==========================================

def search_dux_images(query, max_items):
    """
    Uses the Dux Distributed Global Search (DDGS) library to find images.
    """
    print(f"[*] Connecting to Dux Distributed Global Search (DDGS)...")
    results = []
    
    try:
        # usage is identical to the old library, just the package name changed
        with DDGS() as ddgs:
            print(f"[*] Querying: '{query}'")
            
            # .images() returns a generator
            images_gen = ddgs.images(
                query,
                region="wt-wt",
                safesearch="off",
                max_results=max_items
            )
            results = list(images_gen)
            print(f"[*] Retrieved {len(results)} results from Dux.")
            
    except Exception as e:
        print(f"[!] Dux Search Error: {e}")
    
    return results

def load_image_from_url(url, size=(300, 200)):
    """Downloads and resizes an image for the UI."""
    try:
        # heavy timeout to prevent hanging
        response = requests.get(url, timeout=3)
        response.raise_for_status()
        
        img_data = BytesIO(response.content)
        pil_image = Image.open(img_data)
        pil_image.thumbnail(size) # Resize to thumbnail
        
        return ImageTk.PhotoImage(pil_image)
    except Exception as e:
        print(f"[!] Failed to load image: {e}")
        return None

def main():
    # 1. SEARCH
    results = search_dux_images(SEARCH_QUERY, MAX_RESULTS)
    
    if not results:
        print("No results found. Exiting.")
        return

    # 2. UI SETUP (Tkinter)
    root = tk.Tk()
    root.title(f"Dux Search: {SEARCH_QUERY}")
    
    container = tk.Frame(root, bg="#222")
    container.pack(fill="both", expand=True)

    print("[*] Loading images into UI...")
    
    # Grid layout variables
    row_val = 0
    col_val = 0
    
    for res in results:
        # Prefer thumbnail for speed, fallback to full image
        img_url = res.get('thumbnail') or res.get('image')
        title = res.get('title', 'No Title')

        if not img_url: 
            continue

        tk_img = load_image_from_url(img_url)
        
        if tk_img:
            # Create a card for the image
            frame = tk.Frame(container, bd=2, relief="groove", bg="#333")
            frame.grid(row=row_val, column=col_val, padx=10, pady=10)
            
            # Image
            lbl_img = tk.Label(frame, image=tk_img, bg="#333")
            lbl_img.image = tk_img # Keep reference to prevent garbage collection!
            lbl_img.pack()
            
            # Label
            lbl_txt = tk.Label(frame, text=title[:40]+"...", fg="white", bg="#333")
            lbl_txt.pack()

            # Grid Logic (2 columns wide)
            col_val += 1
            if col_val > 1:
                col_val = 0
                row_val += 1
    
    root.mainloop()

if __name__ == "__main__":
    main()