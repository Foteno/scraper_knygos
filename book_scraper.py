import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests
from bs4 import BeautifulSoup
import urllib.parse
import threading
import queue
import json
import os # Needed to check file existence and get script path
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime # Use datetime for date handling

# --- Configuration ---
BASE_SEARCH_URL = "https://www.knygos.lt/lt/paieska?q="
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
# --- Fixed filename for auto-load/save ---
INTERESTED_BOOKS_FILE = "interested_books.json" # Relative filename

# --- Calculate Absolute Path to the JSON File ---
# Get the directory where the script itself is located
try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError: # Handle cases where __file__ might not be defined (e.g., interactive interpreter)
    SCRIPT_DIR = os.getcwd() # Fallback to current working directory

# Combine the script directory with the filename
INTERESTED_BOOKS_FULL_PATH = os.path.join(SCRIPT_DIR, INTERESTED_BOOKS_FILE)
# --- ---


# --- Scraper for Search Results ---
def scrape_knygos_lt(query):
    """
    Scrapes knygos.lt search results for a given query.

    Args:
        query (str): The search term.

    Returns:
        list: A list of dictionaries with book info (title, price, url, product_id).
              Returns an empty list on error or if nothing found.
        str: An error message string, or None if successful.
    """
    books_found = []
    error_message = None
    try:
        encoded_query = urllib.parse.quote_plus(query)
        search_url = BASE_SEARCH_URL + encoded_query
        print(f"Fetching Search URL: {search_url}") # Keep console log for debugging

        response = requests.get(search_url, headers=HEADERS, timeout=15) # Increased timeout
        response.raise_for_status()
        print("Successfully fetched search page.")

        soup = BeautifulSoup(response.content, 'html.parser')

        # --- Find the main container for products ---
        product_wrapper = soup.find('div', class_='products-holder-wrapper')

        if not product_wrapper:
            print("Could not find 'products-holder-wrapper'. Searching whole page.")
            # Fallback or alternative selectors might be needed here
            product_wrapper = soup # Search whole document as fallback

        # --- Find individual book items *within* the wrapper (or fallback soup) ---
        book_containers = product_wrapper.find_all('div', class_='product-list-item') # Adjust class if needed
        # If the primary selector fails, try another common one
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
                book_data['price'] = title_link_tag.get('data-cta-price', 'N/A') # Default to N/A
                book_data['product_id'] = title_link_tag.get('data-cta-product-id', 'N/A') # Default to N/A

                # Simple representation for display
                book_data['display_text'] = f"{book_data['title']} ({book_data['price']} EUR)"

                if book_data.get('title') and book_data.get('url'): # Ensure we have title and URL
                    books_found.append(book_data)
            # else: # Optional: print if a container didn't yield data
            #     print("Container found, but title/link tag missing inside.")


    except requests.exceptions.Timeout:
        error_message = f"Search request timed out after 15 seconds."
        print(error_message)
    except requests.exceptions.RequestException as e:
        error_message = f"Search network error: {e}"
        print(error_message)
    except Exception as e:
        error_message = f"Search scraping error: {e}"
        print(error_message) # Log the full error

    # Return both results and error status
    return books_found, error_message


# --- Scraper for Individual Book Page & Price History Update ---
def update_book_info(book_data):
    """
    Fetches the individual book page, tries to update its price,
    and records price history.

    Args:
        book_data (dict): Dictionary containing at least 'url' and 'title'.
                          Should also contain 'price_history' list (or it will be created).

    Returns:
        dict: Updated book_data with new price, display_text, and potentially
              updated price_history. Includes 'error' key if update failed.
    """
    # Ensure book_data is a dictionary (safety check)
    if not isinstance(book_data, dict):
        print(f"Error: Received invalid book_data type: {type(book_data)}")
        return {'error': 'Invalid data format', 'title':'Unknown', 'price':'Error', 'url':'N/A', 'product_id':'N/A', 'price_history':[]}


    # Initialize price_history if it doesn't exist or is not a list
    if 'price_history' not in book_data or not isinstance(book_data.get('price_history'), list):
         book_data['price_history'] = []

    # Use a stable identifier for messages
    book_identifier = book_data.get('title', book_data.get('url', 'Unknown Book'))

    if not book_data.get('url'):
        book_data['error'] = "Missing URL"
        book_data['price'] = 'Error'
        book_data['display_text'] = f"{book_identifier} (Update Error: No URL)"
        return book_data

    try:
        print(f"Updating book: {str(book_identifier)[:50]}... URL: {book_data['url']}")
        response = requests.get(book_data['url'], headers=HEADERS, timeout=10)
        response.raise_for_status() # Check for 4xx/5xx errors

        soup = BeautifulSoup(response.content, 'html.parser')

        # --- !!! CRITICAL: SELECTOR FOR PRICE ON PRODUCT PAGE !!! ---
        # This is a GUESS. You MUST inspect the HTML source of a real
        # knygos.lt book page to find the correct selector for the price.
        price_element = soup.select_one('div.product-price span.price, meta[itemprop="price"], span[itemprop="price"]') # Example selector - ADJUST!

        # --- Price History Recording Logic ---
        current_date_str = datetime.today().strftime('%Y-%m-%d') # Get current date as YYYY-MM-DD
        new_price = None
        price_updated = False

        if price_element:
            temp_price = 'N/A'
            if price_element.name == 'meta':
                temp_price = price_element.get('content', 'N/A').strip()
            else:
                # Extract text, remove currency symbols, use dot as decimal separator
                temp_price = price_element.get_text(strip=True).replace('€', '').replace(',', '.').strip()

            # Validate and store the numeric price
            try:
                numeric_price = float(temp_price)
                new_price = f"{numeric_price:.2f}" # Store price with consistent formatting (2 decimal places)
                price_updated = True
                print(f"  -> Found price: {new_price}")
            except (ValueError, TypeError):
                 print(f"  -> Found price element but content is not a valid number: '{temp_price}'")
                 book_data['price'] = 'Parse Error'
                 book_data['display_text'] = f"{book_data.get('title', 'Unknown Title')} (Update Error: Price Format)"
                 book_data.setdefault('error', "Price format error") # Use setdefault

        else:
            # Price element not found
            print("  -> Price element not found on page.")
            book_data['price'] = 'Not Found' # More specific than 'N/A'
            book_data['display_text'] = f"{book_data.get('title', 'Unknown Title')} (Update Error: Price Missing)"
            book_data.setdefault('error', "Price element not found") # Use setdefault

        # Record price if successfully updated
        if price_updated and new_price is not None:
             book_data['price'] = new_price # Update the main price field
             # Ensure title exists before creating display text
             book_title_for_display = book_data.get('title', 'Unknown Title')
             book_data['display_text'] = f"{book_title_for_display} ({book_data['price']} EUR)"

             # Check if history is empty or if date/price differs from the last entry
             last_entry = book_data['price_history'][-1] if book_data['price_history'] else None
             # Compare date string and price string
             if not last_entry or last_entry[0] != current_date_str or last_entry[1] != new_price:
                  print(f"  -> Recording price {new_price} for date {current_date_str}")
                  book_data['price_history'].append([current_date_str, new_price])
             else:
                  print(f"  -> Price {new_price} already recorded for today {current_date_str}")
             # Remove potential 'error' key if price was successfully updated now
             book_data.pop('error', None)

    except requests.exceptions.HTTPError as e:
         error_msg = f"HTTP Error {e.response.status_code}"
         price_status = f'HTTP {e.response.status_code}'
         if e.response.status_code == 404:
            error_msg = "Page not found (404)"
            price_status = 'Not Found (404)'
         print(f"  -> Update failed: {error_msg} for {book_identifier}")
         book_data['price'] = price_status
         book_data['display_text'] = f"{book_data.get('title', 'Unknown Title')} ({price_status})"
         book_data['error'] = error_msg # Store the error status
    except requests.exceptions.Timeout:
        error_msg = "Timeout"
        print(f"  -> Update timed out for {book_identifier}")
        book_data['price'] = 'Timeout'
        book_data['display_text'] = f"{book_data.get('title', 'Unknown Title')} (Update Error: Timeout)"
        book_data['error'] = error_msg
    except requests.exceptions.RequestException as e:
        error_msg = f"Network Error: {e}"
        print(f"  -> Update failed: {error_msg} for {book_identifier}")
        book_data['price'] = 'Network Error'
        book_data['display_text'] = f"{book_data.get('title', 'Unknown Title')} (Update Error: Network)"
        book_data['error'] = error_msg
    except Exception as e:
        error_msg = f"Unknown update error: {e}"
        print(f"  -> Update failed: {error_msg} for {book_identifier}")
        book_data['price'] = 'Update Error'
        book_data['display_text'] = f"{book_data.get('title', 'Unknown Title')} (Update Error: Unknown)"
        book_data['error'] = error_msg

    # Ensure essential keys exist even on error
    book_data.setdefault('title', 'Unknown Title')
    book_data.setdefault('price', 'Error')
    book_data.setdefault('url', 'N/A')
    book_data.setdefault('product_id', 'N/A')
    book_data.setdefault('display_text', f"{book_data['title']} ({book_data['price']})") # Ensure display text reflects current status

    return book_data


# --- Tkinter GUI Application ---
class BookScraperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Knygos.lt Scraper")
        self.root.geometry("850x650") # Slightly wider

        self.search_results = [] # Holds results from the latest search
        # Use product_id or URL as the key for stability during updates
        self.interested_books_by_id = {} # {product_id_or_url: book_data_dict}
                                        # book_data_dict includes 'price_history' list

        self.search_queue = queue.Queue()
        self.update_queue = queue.Queue() # Queue for refresh results

        self.update_tasks_total = 0
        self.update_tasks_done = 0


        # Styling
        style = ttk.Style()
        # Try different themes if 'clam' isn't available or doesn't look good
        try:
            style.theme_use('clam')
        except tk.TclError:
            print("Clam theme not available, using default.")
            # style.theme_use('default') # Or other available themes: 'alt', 'default', 'classic'


        # --- Frames ---
        top_frame = ttk.Frame(root, padding="10")
        top_frame.pack(fill=tk.X, side=tk.TOP)

        middle_frame = ttk.Frame(root, padding="10")
        middle_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        bottom_frame = ttk.Frame(root, padding="10")
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)

        # --- Top Frame: Search Input & Button ---
        ttk.Label(top_frame, text="Search Knygos.lt:").pack(side=tk.LEFT, padx=5)
        self.search_entry = ttk.Entry(top_frame, width=40)
        self.search_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.search_button = ttk.Button(top_frame, text="Search", command=self.start_search)
        self.search_button.pack(side=tk.LEFT, padx=5)

        # --- Middle Frame: Results and Interested Lists ---
        # Configure columns for middle frame to allow resizing
        middle_frame.columnconfigure(0, weight=1) # Results frame column
        middle_frame.columnconfigure(1, weight=0) # Action frame column (fixed width)
        middle_frame.columnconfigure(2, weight=1) # Interested frame column

        # Results List
        results_frame = ttk.LabelFrame(middle_frame, text="Search Results", padding="10")
        # Use grid layout for better resizing control within middle_frame
        results_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        results_frame.rowconfigure(0, weight=1) # Allow listbox to expand vertically
        results_frame.columnconfigure(0, weight=1) # Allow listbox to expand horizontally

        self.results_listbox = tk.Listbox(results_frame, width=50, height=20, selectmode=tk.EXTENDED)
        self.results_listbox.grid(row=0, column=0, sticky="nsew")
        results_scrollbar_y = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.results_listbox.yview)
        results_scrollbar_y.grid(row=0, column=1, sticky="ns")
        self.results_listbox.config(yscrollcommand=results_scrollbar_y.set)
        self.results_listbox.bind('<Double-1>', self.add_selected_to_interested) # Double click to add


        # Action Buttons (between lists)
        action_frame = ttk.Frame(middle_frame)
        action_frame.grid(row=0, column=1, sticky="ns", padx=10, pady=5) # Fixed width column

        self.add_button = ttk.Button(action_frame, text=">> Add >>", command=self.add_selected_to_interested)
        self.add_button.pack(pady=10, anchor='center')
        self.remove_button = ttk.Button(action_frame, text="<< Remove <<", command=self.remove_selected_from_interested)
        self.remove_button.pack(pady=10, anchor='center')


        # Interested List
        interested_frame = ttk.LabelFrame(middle_frame, text="Interested Books (Auto-Refreshed on Load)", padding="10")
        interested_frame.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)
        interested_frame.rowconfigure(0, weight=1) # Allow listbox to expand vertically
        interested_frame.columnconfigure(0, weight=1) # Allow listbox to expand horizontally

        self.interested_listbox = tk.Listbox(interested_frame, width=50, height=20, selectmode=tk.SINGLE) # Change to SINGLE selection for history graph
        self.interested_listbox.grid(row=0, column=0, sticky="nsew")
        interested_scrollbar_y = ttk.Scrollbar(interested_frame, orient=tk.VERTICAL, command=self.interested_listbox.yview)
        interested_scrollbar_y.grid(row=0, column=1, sticky="ns")
        self.interested_listbox.config(yscrollcommand=interested_scrollbar_y.set)
        self.interested_listbox.bind('<Double-1>', self.remove_selected_from_interested) # Double click still removes

        # History Button (below interested list)
        self.history_button = ttk.Button(interested_frame, text="Show Price History", command=self.show_history_graph)
        self.history_button.grid(row=1, column=0, columnspan=2, pady=(10, 0), sticky="ew") # Place below listbox


        # --- Bottom Frame: Save/Load Buttons & Status Label ---
        self.load_button = ttk.Button(bottom_frame, text="Load File...", command=self.prompt_load_interested) # Manual load
        self.load_button.pack(side=tk.LEFT, padx=5)
        self.save_button = ttk.Button(bottom_frame, text="Save Interested", command=self.save_interested)
        self.save_button.pack(side=tk.LEFT, padx=5)

        self.status_label = ttk.Label(bottom_frame, text="Initializing...", anchor='w') # Anchor left
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
        self.search_button.config(state=tk.DISABLED) # Disable button during search
        self.results_listbox.delete(0, tk.END) # Clear previous results
        self.search_results = [] # Clear internal results list

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
            # Process results in the main thread
            self.display_search_results(results, error)
            self.search_button.config(state=tk.NORMAL) # Re-enable button
        except queue.Empty:
            # If queue is empty, check again later
            self.root.after(100, self.check_search_queue) # Check again later

    def display_search_results(self, results, error):
        """Updates the results listbox and status label."""
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
                 # Use the pre-formatted display text
                self.results_listbox.insert(tk.END, book.get('display_text', 'Error displaying book'))


    # --- Interested List Management ---
    def add_selected_to_interested(self, event=None): # Added event=None for double-click binding
        selected_indices = self.results_listbox.curselection()
        if not selected_indices: return

        added_count = 0
        for index in selected_indices:
            selected_display_text = self.results_listbox.get(index)
            # Find the full book data using display text (less robust but simple here)
            book_data = next((b for b in self.search_results if b.get('display_text') == selected_display_text), None)

            if book_data:
                 # Use product_id or URL as the primary key for stability
                 # Prefer product_id if available
                book_key = book_data.get('product_id') if book_data.get('product_id') != 'N/A' else book_data.get('url')

                if book_key and book_key not in self.interested_books_by_id:
                    # --- Initialize price history when adding ---
                    book_data['price_history'] = []
                    # Try to add initial price point if available and valid
                    current_date_str = datetime.today().strftime('%Y-%m-%d')
                    current_price = book_data.get('price')
                    if current_price and current_price != 'N/A':
                        try:
                            # Check if price is valid number before adding
                            float(current_price) # Use the string price directly
                            book_data['price_history'].append([current_date_str, current_price])
                            print(f"Added initial price {current_price} for {book_data.get('title')}")
                        except (ValueError, TypeError):
                            print(f"Initial price '{current_price}' for {book_data.get('title')} is not valid, not adding to history.")
                            pass # Don't add if price is 'N/A' or invalid
                    # --- End initialization ---

                    self.interested_books_by_id[book_key] = book_data.copy() # Store a copy
                    # Add to listbox and immediately refresh view (simple approach)
                    self.refresh_interested_listbox()
                    added_count += 1

        if added_count > 0:
            self.status_label.config(text=f"Added {added_count} book(s) to interested list.")
        # Keep items in results list after adding

    def remove_selected_from_interested(self, event=None): # Added event=None for double-click binding
        selected_indices = self.interested_listbox.curselection()
        if not selected_indices: return

        removed_count = 0
        # Iterate backwards when deleting multiple items by index
        # Since we rebuild the listbox from the dict, it's safer to find the key
        # corresponding to the selection and remove from the dictionary, then refresh.
        keys_to_remove = []
        for index in selected_indices:
            book_display_text = self.interested_listbox.get(index)
            # Find the key (product_id or URL) associated with this display text
            found_key = None
            for key, data in self.interested_books_by_id.items():
                 # Need a reliable way to map listbox item back to dict key
                 # Matching display_text is fragile if it includes changing price/status
                 # Let's match on title + URL/ID as a slightly more robust heuristic
                 # Or, ideally, store the key alongside the text in the listbox (more complex)
                 # Simple approach: Assume title is unique enough for now in the context of deletion
                 if data.get('display_text') == book_display_text:
                     found_key = key
                     break
            if found_key:
                keys_to_remove.append(found_key)

        for key in keys_to_remove:
            if key in self.interested_books_by_id:
                del self.interested_books_by_id[key]
                removed_count += 1

        if removed_count > 0:
            self.refresh_interested_listbox() # Refresh view after removing from dict
            self.status_label.config(text=f"Removed {removed_count} book(s) from interested list.")


    # --- Load & Update Logic ---
    def load_and_update_interested(self):
        """Loads from fixed file and starts background updates."""
        # Use the full path calculated earlier
        if not os.path.exists(INTERESTED_BOOKS_FULL_PATH):
            self.status_label.config(text=f"'{INTERESTED_BOOKS_FILE}' not found in script directory. Add books and save.")
            return

        self.status_label.config(text=f"Loading interested books from {INTERESTED_BOOKS_FILE}...")
        self.interested_listbox.delete(0, tk.END) # Clear display
        self.interested_books_by_id.clear()       # Clear internal data

        try:
            # Open using the full path
            with open(INTERESTED_BOOKS_FULL_PATH, 'r', encoding='utf-8') as f:
                loaded_books_data_list = json.load(f) # Expecting a list of dicts

            if not loaded_books_data_list or not isinstance(loaded_books_data_list, list):
                 self.status_label.config(text="Interested books file is empty or has invalid format.")
                 return

            self.update_tasks_total = 0
            self.update_tasks_done = 0
            valid_books_to_update = []

            # Populate dictionary and prepare update list
            for book_data in loaded_books_data_list:
                 if isinstance(book_data, dict):
                     # Use product_id or URL as key
                     key = book_data.get('product_id') if book_data.get('product_id') != 'N/A' else book_data.get('url')
                     if key:
                        # Ensure essential fields and history list exist
                        book_data.setdefault('price_history', [])
                        book_data.setdefault('title', 'Unknown Title')
                        book_data.setdefault('price', 'N/A')
                        book_data.setdefault('url', 'N/A')
                        book_data.setdefault('product_id', 'N/A')
                        book_data.setdefault('display_text', f"{book_data['title']} ({book_data['price']})")

                        self.interested_books_by_id[key] = book_data # Store loaded data
                        valid_books_to_update.append(book_data) # Add to list for updating
                     else:
                        print(f"Skipping book data with no valid key (product_id or url): {book_data.get('title')}")
                 else:
                    print(f"Skipping invalid entry in JSON file: {book_data}")


            self.update_tasks_total = len(valid_books_to_update)
            if self.update_tasks_total == 0:
                self.status_label.config(text="Load complete. No valid books found to update.")
                return # Nothing to update

            self.status_label.config(text=f"Loaded {len(self.interested_books_by_id)} books. Starting price refresh for {self.update_tasks_total}...")

            # Start update thread for each valid book
            for book_data in valid_books_to_update:
                 update_thread = threading.Thread(target=self.run_update_thread, args=(book_data.copy(),), daemon=True) # Pass a copy
                 update_thread.start()

            # Start checking the update queue
            self.root.after(100, self.check_update_queue)


        except json.JSONDecodeError:
            messagebox.showerror("Load Error", f"File '{INTERESTED_BOOKS_FILE}' is corrupted or not valid JSON.")
            self.status_label.config(text="Error loading interested books (invalid format).")
        except FileNotFoundError:
             messagebox.showerror("Load Error", f"File not found: {INTERESTED_BOOKS_FULL_PATH}")
             self.status_label.config(text="Saved interested books file not found.")
        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load file '{INTERESTED_BOOKS_FILE}': {e}")
            self.status_label.config(text="Error loading interested books.")

    def run_update_thread(self, book_data):
        """Runs the update function and puts results in the update queue."""
        # Ensure the book_data passed is the one to be updated
        updated_data = update_book_info(book_data)
        self.update_queue.put(updated_data)

    def check_update_queue(self):
        """Checks the queue for updated book info."""
        updated = False
        try:
            while not self.update_queue.empty(): # Process all available updates
                updated_data = self.update_queue.get_nowait()
                self.update_tasks_done += 1
                updated = True

                # Use product_id or URL as the key - must match how it was stored initially
                key = updated_data.get('product_id') if updated_data.get('product_id') != 'N/A' else updated_data.get('url')

                if key and key in self.interested_books_by_id:
                    # Update internal dictionary with the refreshed data (including history)
                    self.interested_books_by_id[key] = updated_data
                elif key:
                     print(f"Warning: Received update for unknown key: {key} (Title: {updated_data.get('title')})")
                else:
                     print(f"Warning: Received update for book with no key: {updated_data.get('title')}")

                # Update status label immediately
                progress = f"Updating prices: {self.update_tasks_done}/{self.update_tasks_total} done."
                self.status_label.config(text=progress)


            if self.update_tasks_done >= self.update_tasks_total:
                # All updates finished, now refresh the listbox view cleanly
                print("All update tasks complete. Refreshing listbox.")
                self.refresh_interested_listbox()
                self.status_label.config(text=f"Price refresh complete for {self.update_tasks_total} book(s).")
                # No need to reschedule check_update_queue
            else:
                # If queue was processed but tasks remain, check again later
                self.root.after(200, self.check_update_queue)

        except queue.Empty:
             # Should not happen with while loop unless called when queue is empty AND tasks remain
             if self.update_tasks_done < self.update_tasks_total:
                  self.root.after(200, self.check_update_queue)


    def refresh_interested_listbox(self):
        """Clears and repopulates the interested listbox from the internal dictionary."""
        self.interested_listbox.delete(0, tk.END)
        # Sort items alphabetically by display text before inserting (optional)
        sorted_keys = sorted(self.interested_books_by_id.keys(),
                             key=lambda k: self.interested_books_by_id[k].get('display_text', ''))

        for key in sorted_keys:
            book_data = self.interested_books_by_id[key]
            display_text = book_data.get('display_text', 'Error displaying book')
            self.interested_listbox.insert(tk.END, display_text)
            # Optional: Add color coding based on status/error?
            # if book_data.get('error'):
            #     self.interested_listbox.itemconfig(tk.END, {'fg': 'red'})


    # --- Manual Load / Save ---
    def prompt_load_interested(self):
        """Loads interested books from a user-selected file (manual action)."""
        filepath = filedialog.askopenfilename(
             defaultextension=".json",
             filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
             initialdir=SCRIPT_DIR, # Start Browse in script directory
             title="Load Interested Books File"
        )
        if not filepath: return # User cancelled

        self.status_label.config(text=f"Loading interested books from {os.path.basename(filepath)}...")
        self.interested_listbox.delete(0, tk.END)
        self.interested_books_by_id.clear()

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                loaded_books_data_list = json.load(f) # Expecting a list of dicts

            if not loaded_books_data_list or not isinstance(loaded_books_data_list, list):
                 self.status_label.config(text="Selected file is empty or invalid.")
                 return

            # Update internal dict and listbox directly (no refresh on manual load for simplicity)
            count = 0
            for book_data in loaded_books_data_list:
                 if isinstance(book_data, dict):
                     key = book_data.get('product_id') if book_data.get('product_id') != 'N/A' else book_data.get('url')
                     if key:
                            # Ensure display text exists/is correct based on loaded data
                            book_data.setdefault('price_history', [])
                            book_data.setdefault('title', 'Unknown Title')
                            book_data.setdefault('price', 'N/A')
                            book_data.setdefault('url', 'N/A')
                            book_data.setdefault('product_id', 'N/A')
                            book_data['display_text'] = f"{book_data['title']} ({book_data['price']} EUR)" # Rebuild display text

                            self.interested_books_by_id[key] = book_data
                            count += 1
                 else:
                      print(f"Skipping invalid entry during manual load: {book_data}")

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
            initialdir=SCRIPT_DIR, # Start Browse in script directory
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

    # --- Graphing Method ---
    def show_history_graph(self):
        """Displays a price history graph for the selected interested book."""
        selected_indices = self.interested_listbox.curselection()

        if not selected_indices:
            messagebox.showwarning("Selection Error", "Please select a book from the 'Interested Books' list.")
            return
        # No check for multiple selections needed as listbox mode is SINGLE

        selected_index = selected_indices[0]
        selected_display_text = self.interested_listbox.get(selected_index)

        # Find the book data using the display text (less robust, find key instead)
        book_data = None
        found_key = None
        # Iterate through dictionary to find the key corresponding to the selected display text
        # This mapping is fragile if display text changes format or isn't unique
        for key, data in self.interested_books_by_id.items():
             if data.get('display_text') == selected_display_text:
                  book_data = data
                  found_key = key # Keep track of the key if needed
                  break

        if not book_data:
             # Fallback: Try matching title part? More complex.
             messagebox.showerror("Error", f"Could not find internal data for '{selected_display_text}'. Try refreshing/reloading.")
             return

        history = book_data.get('price_history', [])
        book_title = book_data.get('title', 'Unknown Book')

        # Filter out potential invalid entries before checking length
        valid_history = []
        for entry in history:
            if isinstance(entry, list) and len(entry) == 2:
                try:
                    # Attempt conversion to ensure data is usable
                    datetime.strptime(entry[0], '%Y-%m-%d')
                    float(entry[1])
                    valid_history.append(entry)
                except (ValueError, TypeError):
                    print(f"Skipping invalid history entry for {book_title}: {entry}")
            else:
                 print(f"Skipping malformed history entry for {book_title}: {entry}")


        if not valid_history or len(valid_history) < 2:
             messagebox.showinfo("Price History", f"Not enough valid price history recorded for '{book_title}' to plot a line graph (Need at least 2 points). Found {len(valid_history)} valid points.")
             # Optionally, show a message even with 1 point?
             # if len(valid_history) == 1:
             #     messagebox.showinfo("Price History", f"Only one price point recorded for '{book_title}': {valid_history[0][1]} EUR on {valid_history[0][0]}.")
             return

        # Prepare data for plotting
        dates = []
        prices = []
        try:
            # Use the filtered valid_history
            for entry in valid_history:
                 # entry = ['YYYY-MM-DD', 'price_str']
                 date_obj = datetime.strptime(entry[0], '%Y-%m-%d').date() # Convert string to date object
                 price_float = float(entry[1]) # Convert price string to float
                 dates.append(date_obj)
                 prices.append(price_float)
        except Exception as e: # Catch any parsing error missed by filtering
             messagebox.showerror("History Data Error", f"Critical error parsing price history data: {e}")
             return

        # Plotting using Matplotlib
        try:
            # Check available styles, provide fallbacks
            available_styles = plt.style.available
            if 'seaborn-v0_8-darkgrid' in available_styles:
                 plt.style.use('seaborn-v0_8-darkgrid')
            elif 'seaborn-darkgrid' in available_styles:
                 plt.style.use('seaborn-darkgrid')
            elif 'ggplot' in available_styles:
                 plt.style.use('ggplot')
            else:
                 print("Preferred styles not found, using default Matplotlib style.")
                 # Use default

            fig, ax = plt.subplots(figsize=(10, 5)) # Create figure and axes

            ax.plot_date(dates, prices, linestyle='-', label=f'{book_title}') # Use plot_date for date objects

            # Formatting the plot
            ax.set_title(f"Price History for '{book_title}'")
            ax.set_xlabel("Date")
            ax.set_ylabel("Price (EUR)")
            ax.grid(True, which='both', linestyle='--', linewidth=0.5) # Add grid

            # Format x-axis dates nicely
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=10)) # Auto-locate ticks reasonably
            fig.autofmt_xdate(rotation=30, ha='right') # Auto-rotate date labels

            # Add interactivity (zoom/pan) automatically enabled by plt.show() usually
            # Add value labels to points (optional, can clutter if many points)
            # for i, txt in enumerate(prices):
            #    ax.annotate(f"{txt:.2f}", (dates[i], prices[i]), textcoords="offset points", xytext=(0,5), ha='center')


            plt.tight_layout() # Adjust layout to prevent labels overlapping
            # plt.legend() # Legend might be redundant if only one line
            plt.show() # Display the plot in a new window

        except Exception as e:
             messagebox.showerror("Graphing Error", f"An error occurred while generating the graph: {e}")


# --- Run the Application ---
if __name__ == "__main__":
    # Ensure the directory for the JSON file exists (optional, good practice)
    # os.makedirs(SCRIPT_DIR, exist_ok=True)

    root = tk.Tk()
    app = BookScraperApp(root)
    root.mainloop()