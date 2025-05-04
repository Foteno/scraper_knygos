# Knygos.lt Personal Book Tracker & Price Monitor

**Date:** May 4, 2025

## Overview

This custom-built Python application serves as a personalized tool designed to help you keep track of books you are interested in purchasing from the Lithuanian online bookstore, `knygos.lt`. Its core purpose is not just to maintain a wishlist but also to **actively monitor and record the price history** of these books over time, empowering you to make more informed purchasing decisions based on price trends and potential sales.

## How It Works

The application provides a user-friendly graphical interface (GUI) to manage your book tracking process:

1.  **Search:** You can search for books directly on `knygos.lt` using the integrated search feature within the application.
2.  **Add to Watchlist:** From the search results, you can select books you're interested in and add them to your personal "Interested Books" watchlist.
3.  **Save Locally:** This personalized watchlist, including essential book details like title, URL, and ID, is saved locally in a file named `interested_books.json` in the application's directory.
4.  **Auto-Load & Refresh:** When you launch the application, it **automatically loads** your saved watchlist from the `interested_books.json` file. Crucially, it then **attempts to automatically visit** the `knygos.lt` page for each book on your list to check its **current price**.
5.  **Record Price History:** If the price check is successful, the application **records the current date and the fetched price**. This data point is added to a historical log maintained for each specific book within the saved file, but only if it's the first check for that day or if the price has changed since the last recorded entry.
6.  **Visualize Trends:** By accumulating this price data over days, weeks, and months, the application allows you to select any book from your watchlist and view its price history as a simple line graph, showing how its price has fluctuated over the recorded period.

## Key Features

* **Knygos.lt Search:** Directly search the bookstore from within the app.
* **Personal Watchlist:** Maintain and manage your list of desired books ("Interested Books").
* **Local Data Storage:** Your list and price history are saved locally (`interested_books.json`).
* **Automatic Price Refresh:** Checks current prices of saved books on startup.
* **Price History Logging:** Automatically records date and price data over time.
* **Price Trend Graph:** Visualizes the price history for any selected book.
* **Graphical User Interface:** Provides an easy-to-use interface for all functions.

## Benefits for Purchase Planning

This tool transforms a simple wishlist into a strategic purchasing aid. By observing the price history graph for a specific book, you can:

* Identify typical price points and fluctuations.
* Recognize potential sales or significant price drops.
* Decide whether to buy now or wait for a better price based on historical trends.
* Avoid manually checking prices for multiple books regularly.

## Technical Foundation

The application is built using `Python` and relies on several key libraries: `requests` and `BeautifulSoup4` for web scraping `knygos.lt`, `Tkinter` for the graphical interface, and `Matplotlib` for generating the price history graphs. It's important to note that web scrapers depend heavily on the target website's structure; changes to `knygos.lt` may require updates to the script's selectors to maintain functionality.

## Conclusion

This application provides a dedicated and automated solution tailored to your goal of tracking desired books from `knygos.lt`. By combining a convenient watchlist with automatic price checking and historical visualization, it offers valuable insights to help you decide the best time to make your purchase.