# Knygos.lt Book Scraper GUI

A Python application with a graphical user interface (GUI) to search for books on knygos.lt, save a list of interested books, and automatically refresh their price information on startup.

## Features

* Search for books on knygos.lt by title or keyword.
* Display search results (Title, Price).
* Maintain a separate list of "Interested Books".
* Save the "Interested Books" list to a local file (`interested_books.json`).
* Automatically load the saved list on application startup.
* Automatically attempt to refresh the price for each saved book on startup by visiting its page.
* GUI built with Python's built-in Tkinter library.

## Requirements

* Python 3.6 or higher (Download from [python.org](https://www.python.org/))
* `pip` (Python package installer, usually included with Python)

## Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd <repository-directory>
    ```
    Replace `<your-repository-url>` with the actual URL of your GitHub repository and `<repository-directory>` with the name of the folder created by cloning.

2.  **Create `requirements.txt`:**
    Create a file named `requirements.txt` in the repository's main directory and add the following lines:
    ```txt
    requests
    beautifulsoup4
    ```

3.  **Install dependencies:**
    Open a terminal or command prompt in the repository directory and run:
    ```bash
    pip install -r requirements.txt
    ```

## Running the Application

Navigate to the repository directory in your terminal and run the main script:

```bash
python book_scraper.py