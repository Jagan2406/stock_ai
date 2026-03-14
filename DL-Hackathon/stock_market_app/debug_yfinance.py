import yfinance as yf


ticker = "MSFT"

stock = yf.Ticker(ticker)
hist = stock.history(period="3mo")

print("Ticker:", ticker)
print("Is Empty:", hist.empty)
print("Rows:", len(hist))
print(hist.tail())
def test_fetch(ticker):
    print(f"Attempting to fetch data for {ticker}...")
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1mo")
        if hist.empty:
            print(f"Success: Connected, but no data found for {ticker}. (This might be a valid symbol with no recent data, or a data source issue)")
        else:
            print(f"Success: Fetched {len(hist)} rows for {ticker}.")
            print(hist.head())
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_fetch("AAPL")
    test_fetch("MSFT")
    test_fetch("INFY.NS")
