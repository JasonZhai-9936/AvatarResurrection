import tkinter as tk
import webbrowser
from io import BytesIO
import requests
from PIL import Image, ImageTk
from ddgs import DDGS

# ==========================================
# CONFIGURATION
# ==========================================
SEARCH_QUERY = "Charles Darwin"
MAX_RESULTS = 4
VIDEO_DURATION = "short"  # Options: 'short', 'medium', 'long'
# ==========================================

def search_dux_videos(query, max_items):
    print(f"[*] Connecting to Dux (DDGS)...")
    results = []
    
    try:
        with DDGS() as ddgs:
            print(f"[*] Querying for '{VIDEO_DURATION}' videos: '{query}'")
            
            # ADDED duration parameter here
            videos_gen = ddgs.videos(
                query,
                region="wt-wt",
                safesearch="off",
                max_results=max_items,
                duration=VIDEO_DURATION  # <--- NEW FILTER
            )
            results = list(videos_gen)
            print(f"[*] Retrieved {len(results)} videos.")
            
    except Exception as e:
        print(f"[!] Dux Video Search Error: {e}")
    
    return results

def load_image_from_url(url, size=(300, 200)):
    try:
        if not url: return None
        response = requests.get(url, timeout=3)
        response.raise_for_status()
        img_data = BytesIO(response.content)
        pil_image = Image.open(img_data)
        pil_image.thumbnail(size)
        return ImageTk.PhotoImage(pil_image)
    except Exception:
        return None

def open_link(url):
    if url: webbrowser.open(url)

def main():
    results = search_dux_videos(SEARCH_QUERY, MAX_RESULTS)
    
    if not results:
        print("No results found.")
        return

    root = tk.Tk()
    root.title(f"Dux Short Videos: {SEARCH_QUERY}")
    
    container = tk.Frame(root, bg="#222")
    container.pack(fill="both", expand=True)

    row_val = 0
    col_val = 0
    
    for res in results:
        title = res.get('title', 'No Title')
        video_url = res.get('content')
        
        # Get thumbnail
        images_dict = res.get('images', {})
        thumb_url = images_dict.get('medium') or images_dict.get('large') or res.get('image')

        tk_img = load_image_from_url(thumb_url)
        
        if tk_img:
            frame = tk.Frame(container, bd=2, relief="groove", bg="#333")
            frame.grid(row=row_val, column=col_val, padx=10, pady=10)
            
            # Thumbnail
            lbl_img = tk.Label(frame, image=tk_img, bg="black", cursor="hand2")
            lbl_img.image = tk_img
            lbl_img.pack()
            lbl_img.bind("<Button-1>", lambda e, url=video_url: open_link(url))
            
            # Title
            display_title = (title[:35] + '...') if len(title) > 35 else title
            lbl_txt = tk.Label(frame, text=display_title, fg="white", bg="#333", 
                               font=("Arial", 10, "bold"), cursor="hand2")
            lbl_txt.pack(pady=5)
            lbl_txt.bind("<Button-1>", lambda e, url=video_url: open_link(url))

            # Show Duration Label
            duration_txt = res.get('duration', 'Unknown')
            lbl_meta = tk.Label(frame, text=f"Duration: {duration_txt}", fg="#0f0", bg="#333", font=("Arial", 8))
            lbl_meta.pack(pady=(0, 5))

            col_val += 1
            if col_val > 1:
                col_val = 0
                row_val += 1
    
    root.mainloop()

if __name__ == "__main__":
    main()