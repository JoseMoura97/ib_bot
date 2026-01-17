import quiverquant
import os
from dotenv import load_dotenv

load_dotenv()
QUIVER_API_KEY = os.getenv('QUIVER_API_KEY')

def inspect_quiver():
    quiver = quiverquant.quiver(QUIVER_API_KEY)
    print("Fetching congress trading...")
    trades = quiver.congress_trading()
    if not trades.empty:
        print("Columns in congress_trading:", trades.columns.tolist())
        print(trades.head(1))
    else:
        print("No congress trades found.")

    print("\nFetching insiders...")
    insiders = quiver.insiders()
    if not insiders.empty:
        print("Columns in insiders:", insiders.columns.tolist())
    else:
        print("No insiders found.")

if __name__ == "__main__":
    inspect_quiver()
