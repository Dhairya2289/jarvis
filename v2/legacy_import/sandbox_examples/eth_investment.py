import sys

def main():
    if len(sys.argv) != 3:
        print("Usage: python eth_investment.py <current_price> <change_24h>")
        return
    
    current_price = float(sys.argv[1])
    change_24h = float(sys.argv[2])
    
    # Calculate yesterday's price
    yesterday_price = current_price / (1 + (change_24h/100))
    
    # Calculate current value of 1000 ETH investment
    investment_eth = 1000
    current_value = investment_eth * current_price
    
    print(f"Yesterday's price: ${yesterday_price:.2f}")
    print(f"Current value of {investment_eth} ETH investment: ${current_value:,.2f}")

if __name__ == "__main__":
    main()