import os # Needed to check file existence
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests
from bs4 import BeautifulSoup
import urllib.parse
import threading
import queue
import json

# --- Configuration ---
BASE_SEARCH_URL = "https://www.knygos.lt/lt/paieska?q="
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
# --- Fixed filename for auto-load/save ---
INTERESTED_BOOKS_FILE = "interested_books.json"
# --- Calculate Absolute Path to the JSON File ---
# Get the directory where the script itself is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Combine the script directory with the filename
INTERESTED_BOOKS_FULL_PATH = os.path.join(SCRIPT_DIR, INTERESTED_BOOKS_FILE)
# --- ---

# --- Scraper for Search Results (Unchanged) ---
def scrape_knygos_lt(query):
    # ... (keep the previous scrape_knygos_lt function exactly as it was) ...
    books_found = []
    error_message = None
    try:
        encoded_query = urllib.parse.quote_plus(query)
        search_url = BASE_SEARCH_URL + encoded_query
        print(f"Fetching Search URL: {search_url}")

        response = requests.get(search_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        print("Successfully fetched search page.")

        soup = BeautifulSoup(response.content, 'html.parser')
        product_wrapper = soup.find('div', class_='products-holder-wrapper')
        if not product_wrapper:
            print("Could not find 'products-holder-wrapper'. Searching whole page.")
            product_wrapper = soup

        book_containers = product_wrapper.find_all('div', class_='product')
        if not book_containers:
             book_containers = product_wrapper.find_all('div', class_='col-product')

        print(f"Found {len(book_containers)} potential book container(s) in search results.")

        if not book_containers and product_wrapper == soup : # Only report error if not found anywhere
             error_message = "No book containers found using known selectors in search results."

        for container in book_containers:
            book_data = {}
            title_link_tag = container.select_one('div.book-properties h2 a')
            if title_link_tag:
                book_data['title'] = title_link_tag.get_text(strip=True)
                relative_url = title_link_tag.get('href')
                if relative_url:
                    book_data['url'] = urllib.parse.urljoin('https://www.knygos.lt', relative_url)
                else:
                    book_data['url'] = None # Handle cases where URL might be missing
                book_data['price'] = title_link_tag.get('data-cta-price', 'N/A')
                book_data['product_id'] = title_link_tag.get('data-cta-product-id', 'N/A')
                book_data['display_text'] = f"{book_data['title']} ({book_data['price']} EUR)"
                if book_data.get('title') and book_data.get('url'): # Ensure we have title and URL
                    books_found.append(book_data)

    except requests.exceptions.Timeout:
        error_message = f"Search request timed out."
        print(error_message)
    except requests.exceptions.RequestException as e:
        error_message = f"Search network error: {e}"
        print(error_message)
    except Exception as e:
        error_message = f"Search scraping error: {e}"
        print(error_message)
    return books_found, error_message


# --- NEW: Scraper for Individual Book Page ---
def update_book_info(book_data):
    """
    Fetches the individual book page and tries to update its price.

    Args:
        book_data (dict): Dictionary containing at least 'url' and 'title'.

    Returns:
        dict: Updated book_data with new price and display_text,
              or original book_data with an 'error' key if update failed.
    """
    if not book_data.get('url'):
        book_data['error'] = "Missing URL"
        book_data['price'] = 'Error'
        book_data['display_text'] = f"{book_data.get('title', 'Unknown Title')} (Update Error: No URL)"
        return book_data

    try:
        print(f"Updating book: {book_data.get('title', 'Unknown')[:30]}... URL: {book_data['url']}")
        response = requests.get(book_data['url'], headers=HEADERS, timeout=10)
        response.raise_for_status() # Check for 4xx/5xx errors

        soup = BeautifulSoup(response.content, 'html.parser')

        # --- !!! CRITICAL: SELECTOR FOR PRICE ON PRODUCT PAGE !!! ---
        # This is a GUESS. You MUST inspect the HTML source of a real
        # knygos.lt book page to find the correct selector for the price.
        # Common patterns:
        # - A span/div with class 'price' inside a specific container
        # - A meta tag: <meta itemprop="price" content="9.99">
        # - An element with a specific ID
        price_element = soup.select_one('div.new-price') # Example selector - ADJUST!

        if price_element:
            new_price = 'N/A'
            if price_element.name == 'meta':
                new_price = price_element.get('content', 'N/A').strip()
            else:
                new_price = price_element.get_text(strip=True).replace('€', '').replace(',', '.').strip() # Clean up price text

            # Validate price format slightly (optional)
            try:
                float(new_price)
                book_data['price'] = new_price
                book_data['display_text'] = f"{book_data['title']} ({book_data['price']} EUR)"
                print(f"  -> Updated price: {new_price}")
            except ValueError:
                 print(f"  -> Found price element but content is not a number: '{new_price}'")
                 book_data['price'] = 'Parse Error'
                 book_data['display_text'] = f"{book_data['title']} (Update Error: Price Format)"
                 book_data['error'] = "Price format error"

        else:
            # Price element not found
            print("  -> Price element not found on page.")
            book_data['price'] = 'Not Found'
            book_data['display_text'] = f"{book_data['title']} (Update Error: Price Missing)"
            book_data['error'] = "Price element not found"

    except requests.exceptions.HTTPError as e:
         if e.response.status_code == 404:
            print(f"  -> Update failed: Page not found (404) for {book_data['title']}")
            book_data['price'] = 'Not Found (404)'
            book_data['display_text'] = f"{book_data['title']} (Not Found)"
            book_data['error'] = "404 Not Found"
         else:
            print(f"  -> Update failed: HTTP Error {e.response.status_code} for {book_data['title']}")
            book_data['price'] = f'HTTP Error {e.response.status_code}'
            book_data['display_text'] = f"{book_data['title']} (Update Error: HTTP)"
            book_data['error'] = f"HTTP Error {e.response.status_code}"
    except requests.exceptions.Timeout:
        print(f"  -> Update timed out for {book_data['title']}")
        book_data['price'] = 'Timeout'
        book_data['display_text'] = f"{book_data['title']} (Update Error: Timeout)"
        book_data['error'] = "Timeout"
    except requests.exceptions.RequestException as e:
        print(f"  -> Update failed: Network Error for {book_data['title']}: {e}")
        book_data['price'] = 'Network Error'
        book_data['display_text'] = f"{book_data['title']} (Update Error: Network)"
        book_data['error'] = "Network Error"
    except Exception as e:
        print(f"  -> Update failed: Unknown Error for {book_data['title']}: {e}")
        book_data['price'] = 'Update Error'
        book_data['display_text'] = f"{book_data['title']} (Update Error: Unknown)"
        book_data['error'] = f"Unknown update error: {e}"

    # Ensure essential keys exist even on error
    book_data.setdefault('title', 'Unknown Title')
    book_data.setdefault('price', 'Error')
    book_data.setdefault('url', 'N/A')
    book_data.setdefault('product_id', 'N/A')

    return book_data


# --- Tkinter GUI Application ---
class BookScraperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Knygos.lt Scraper")
        self.root.geometry("850x650") # Slightly wider

        self.search_results = []
        self.interested_books = {} # {display_text_key: book_data} - Key might change on update! Using URL as key might be more stable. Let's try product_id or URL.
        self.interested_books_by_id = {} # {product_id_or_url: book_data} - MORE STABLE KEY

        self.search_queue = queue.Queue()
        self.update_queue = queue.Queue() # Queue for refresh results

        self.update_tasks_total = 0
        self.update_tasks_done = 0


        # Styling
        style = ttk.Style()
        style.theme_use('clam')

        # --- Frames ---
        top_frame = ttk.Frame(root, padding="10")
        top_frame.pack(fill=tk.X)

        middle_frame = ttk.Frame(root, padding="10")
        middle_frame.pack(fill=tk.BOTH, expand=True)

        bottom_frame = ttk.Frame(root, padding="10")
        bottom_frame.pack(fill=tk.X)

        # --- Top Frame: Search Input & Button ---
        ttk.Label(top_frame, text="Search Knygos.lt:").pack(side=tk.LEFT, padx=5)
        self.search_entry = ttk.Entry(top_frame, width=40)
        self.search_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.search_button = ttk.Button(top_frame, text="Search", command=self.start_search)
        self.search_button.pack(side=tk.LEFT, padx=5)

        # --- Middle Frame: Results and Interested Lists ---
        results_frame = ttk.LabelFrame(middle_frame, text="Search Results", padding="10")
        results_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        self.results_listbox = tk.Listbox(results_frame, width=50, height=20, selectmode=tk.EXTENDED)
        self.results_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        results_scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.results_listbox.yview)
        results_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.results_listbox.config(yscrollcommand=results_scrollbar.set)
        self.results_listbox.bind('<Double-1>', self.add_selected_to_interested)

        action_frame = ttk.Frame(middle_frame)
        action_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10)
        self.add_button = ttk.Button(action_frame, text=">> Add >>", command=self.add_selected_to_interested)
        self.add_button.pack(pady=10)
        self.remove_button = ttk.Button(action_frame, text="<< Remove <<", command=self.remove_selected_from_interested)
        self.remove_button.pack(pady=10)

        interested_frame = ttk.LabelFrame(middle_frame, text="Interested Books (Auto-Refreshed on Load)", padding="10")
        interested_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        self.interested_listbox = tk.Listbox(interested_frame, width=50, height=20, selectmode=tk.EXTENDED)
        self.interested_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        interested_scrollbar = ttk.Scrollbar(interested_frame, orient=tk.VERTICAL, command=self.interested_listbox.yview)
        interested_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.interested_listbox.config(yscrollcommand=interested_scrollbar.set)
        self.interested_listbox.bind('<Double-1>', self.remove_selected_from_interested)

        # --- Bottom Frame: Buttons & Status Label ---
        self.load_button = ttk.Button(bottom_frame, text="Load File...", command=self.prompt_load_interested) # Manual load
        self.load_button.pack(side=tk.LEFT, padx=5)
        self.save_button = ttk.Button(bottom_frame, text="Save Interested", command=self.save_interested)
        self.save_button.pack(side=tk.LEFT, padx=5)
        self.status_label = ttk.Label(bottom_frame, text="Initializing...")
        self.status_label.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        # --- Initial Load & Refresh ---
        self.root.after(100, self.load_and_update_interested) # Start auto-load after GUI is set up

    # --- Search Handling ---
    def start_search(self):
        query = self.search_entry.get().strip()
        if not query:
            messagebox.showwarning("Input Error", "Please enter a search term.")
            return
        self.status_label.config(text=f"Searching for '{query}'...")
        self.search_button.config(state=tk.DISABLED)
        self.results_listbox.delete(0, tk.END)
        self.search_results = []
        # Start scraper in a new thread
        self.search_thread = threading.Thread(target=self.run_search_thread, args=(query,), daemon=True)
        self.search_thread.start()
        # Schedule queue check
        self.root.after(100, self.check_search_queue)

    def run_search_thread(self, query):
        """Runs the search scraper and puts results in the queue."""
        results, error = scrape_knygos_lt(query)
        self.search_queue.put((results, error))

    def check_search_queue(self):
        """Checks the queue for search results."""
        try:
            results, error = self.search_queue.get_nowait()
            self.display_search_results(results, error)
            self.search_button.config(state=tk.NORMAL)
        except queue.Empty:
            self.root.after(100, self.check_search_queue) # Check again later

    def display_search_results(self, results, error):
        """Updates the results listbox."""
        self.results_listbox.delete(0, tk.END)
        self.search_results = results
        if error:
            self.status_label.config(text=f"Search Error: {error}")
            messagebox.showerror("Search Error", error)
        elif not results:
            self.status_label.config(text="Search complete. No books found.")
        else:
            self.status_label.config(text=f"Search complete. Found {len(results)} book(s).")
            for book in results:
                self.results_listbox.insert(tk.END, book.get('display_text', 'Error displaying book'))

    # --- Interested List Management ---
    def add_selected_to_interested(self, event=None):
        selected_indices = self.results_listbox.curselection()
        if not selected_indices: return

        added_count = 0
        for index in selected_indices:
            selected_display_text = self.results_listbox.get(index)
            # Find the full book data using display text (less robust but simple here)
            book_data = next((b for b in self.search_results if b.get('display_text') == selected_display_text), None)

            if book_data:
                 # Use product_id or URL as the primary key for stability
                book_key = book_data.get('product_id') or book_data.get('url')
                if book_key and book_key not in self.interested_books_by_id:
                    self.interested_books_by_id[book_key] = book_data
                    # Find where to insert to keep listbox sorted alphabetically (optional)
                    # current_items = self.interested_listbox.get(0, tk.END)
                    # insert_pos = tk.END # Find appropriate position
                    self.interested_listbox.insert(tk.END, book_data['display_text'])
                    added_count += 1

        if added_count > 0:
            self.status_label.config(text=f"Added {added_count} book(s) to interested list.")
        # Keep items in results list after adding

    def remove_selected_from_interested(self, event=None):
        selected_indices = self.interested_listbox.curselection()
        if not selected_indices: return

        removed_count = 0
        # Iterate backwards when deleting multiple items by index
        for index in sorted(selected_indices, reverse=True):
            book_display_text = self.interested_listbox.get(index)
            # Find the key (product_id or URL) associated with this display text to remove from dict
            book_key_to_remove = None
            for key, data in self.interested_books_by_id.items():
                 # Need to handle potential updates to display_text
                 # Check current display text and maybe original title/id? Safer to rely on index.
                 # For simplicity here, we assume display_text is unique enough *at the moment of deletion*
                 # A more robust way might store the key directly in the listbox item or use a parallel list.
                 if data.get('display_text') == book_display_text: # Less robust if text updated!
                      book_key_to_remove = key
                      break

            if book_key_to_remove and book_key_to_remove in self.interested_books_by_id:
                del self.interested_books_by_id[book_key_to_remove]
                removed_count += 1

            self.interested_listbox.delete(index) # Delete from listbox by index

        if removed_count > 0:
            self.status_label.config(text=f"Removed {removed_count} book(s) from interested list.")


    # --- Load & Update Logic ---
    def load_and_update_interested(self):
        """Loads from fixed file and starts background updates."""
        if not os.path.exists(INTERESTED_BOOKS_FULL_PATH):
            self.status_label.config(text=f"'{INTERESTED_BOOKS_FILE}' not found. Add books and save.")
            return

        self.status_label.config(text=f"Loading interested books from {INTERESTED_BOOKS_FILE}...")
        self.interested_listbox.delete(0, tk.END) # Clear display
        self.interested_books_by_id.clear()       # Clear internal data

        try:
            with open(INTERESTED_BOOKS_FULL_PATH, 'r', encoding='utf-8') as f:
                loaded_books_data = json.load(f)

            if not loaded_books_data:
                 self.status_label.config(text="Interested books file is empty.")
                 return

            self.update_tasks_total = len(loaded_books_data)
            self.update_tasks_done = 0
            self.status_label.config(text=f"Loaded {self.update_tasks_total} books. Starting price refresh...")

            # Start update thread for each book
            for book_data in loaded_books_data:
                 # Use product_id or URL as key, ensure book_data is dict
                 if isinstance(book_data, dict) and (book_data.get('product_id') or book_data.get('url')):
                    # Start update task
                    update_thread = threading.Thread(target=self.run_update_thread, args=(book_data,), daemon=True)
                    update_thread.start()
                 else:
                    print(f"Skipping invalid book data during load: {book_data}")
                    self.update_tasks_total -= 1 # Adjust total count

            # Start checking the update queue
            if self.update_tasks_total > 0:
                 self.root.after(100, self.check_update_queue)
            else:
                 self.status_label.config(text="Load complete. No valid books found to update.")


        except json.JSONDecodeError:
            messagebox.showerror("Load Error", f"File '{INTERESTED_BOOKS_FILE}' is corrupted.")
            self.status_label.config(text="Error loading interested books (invalid format).")
        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load file '{INTERESTED_BOOKS_FILE}': {e}")
            self.status_label.config(text="Error loading interested books.")

    def run_update_thread(self, book_data):
        """Runs the update function and puts results in the update queue."""
        updated_data = update_book_info(book_data)
        self.update_queue.put(updated_data)

    def check_update_queue(self):
        """Checks the queue for updated book info."""
        try:
            while not self.update_queue.empty(): # Process all available updates
                updated_data = self.update_queue.get_nowait()
                self.update_tasks_done += 1

                # Use product_id or URL as the key
                book_key = updated_data.get('product_id') or updated_data.get('url')

                if book_key:
                    # Update internal dictionary
                    self.interested_books_by_id[book_key] = updated_data

                    # Update listbox (more complex: find and replace or rebuild)
                    # Simple approach: rebuild listbox after all updates (might cause flicker)
                    # Better: find item by key/old text and update/insert
                    # For simplicity now: Add updated item to end. We'll rebuild at the end.
                    # This requires a final step to clear and repopulate the listbox cleanly.

                # Update status
                progress = f"Updating prices: {self.update_tasks_done}/{self.update_tasks_total} done."
                self.status_label.config(text=progress)


            if self.update_tasks_done >= self.update_tasks_total:
                # All updates finished, now refresh the listbox view cleanly
                self.refresh_interested_listbox()
                self.status_label.config(text=f"Price refresh complete for {self.update_tasks_total} book(s).")
            else:
                # If queue was emptied but tasks remain, check again later
                self.root.after(200, self.check_update_queue)

        except queue.Empty:
             # Should not happen with while loop, but check again if tasks remain
             if self.update_tasks_done < self.update_tasks_total:
                  self.root.after(200, self.check_update_queue)


    def refresh_interested_listbox(self):
        """Clears and repopulates the interested listbox from the internal dictionary."""
        self.interested_listbox.delete(0, tk.END)
        # Sort items alphabetically by display text before inserting (optional)
        sorted_items = sorted(self.interested_books_by_id.values(), key=lambda x: x.get('display_text', ''))
        for book_data in sorted_items:
            self.interested_listbox.insert(tk.END, book_data.get('display_text', 'Error displaying book'))


    # --- Manual Load / Save ---
    def prompt_load_interested(self):
        """Loads interested books from a user-selected file (manual action)."""
        filepath = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=SCRIPT_DIR, # Suggest starting the dialog in the script's directory
            title="Load Interested Books File"
        )
        if not filepath: return # User cancelled

        self.status_label.config(text=f"Loading interested books from {os.path.basename(filepath)}...")
        self.interested_listbox.delete(0, tk.END)
        self.interested_books_by_id.clear()

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                loaded_books_data = json.load(f)

            if not loaded_books_data:
                 self.status_label.config(text="Selected file is empty.")
                 return

            # Update internal dict and listbox directly (no refresh on manual load for simplicity)
            count = 0
            for book_data in loaded_books_data:
                 if isinstance(book_data, dict):
                      book_key = book_data.get('product_id') or book_data.get('url')
                      if book_key:
                            # Ensure display text exists
                            book_data['display_text'] = book_data.get('display_text', f"{book_data.get('title', 'N/A')} ({book_data.get('price', 'N/A')} EUR)")
                            self.interested_books_by_id[book_key] = book_data
                            count += 1
                 else:
                      print(f"Skipping invalid book data during manual load: {book_data}")

            self.refresh_interested_listbox() # Refresh view from dictionary
            self.status_label.config(text=f"Loaded {count} interested books from {os.path.basename(filepath)}.")

        except FileNotFoundError:
             messagebox.showerror("Load Error", f"File not found: {filepath}")
             self.status_label.config(text="File not found.")
        except json.JSONDecodeError:
             messagebox.showerror("Load Error", f"File is corrupted or not valid JSON: {filepath}")
             self.status_label.config(text="Error loading file (invalid format).")
        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load file: {e}")
            self.status_label.config(text="Error loading file.")


    def save_interested(self):
        """Saves the *current* interested books list to a JSON file."""
        if not self.interested_books_by_id:
            messagebox.showinfo("Save", "Interested list is empty. Nothing to save.")
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=INTERESTED_BOOKS_FULL_PATH, # Use the calculated full path as default suggestion
            title="Save Interested Books As..."
        )
        if not filepath: return # User cancelled

        try:
            # Save the values (book data dictionaries) from the interested_books dict
            books_to_save = list(self.interested_books_by_id.values())
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(books_to_save, f, ensure_ascii=False, indent=4)
            self.status_label.config(text=f"Interested books saved to {os.path.basename(filepath)}")
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save file: {e}")
            self.status_label.config(text="Error saving interested books.")


# --- Run the Application ---
if __name__ == "__main__":
    root = tk.Tk()
    app = BookScraperApp(root)
    root.mainloop()