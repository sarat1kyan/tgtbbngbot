import time
import logging
import pandas as pd
from binance.client import Client
from ta.trend import SMAIndicator, EMAIndicator, MACD
from ta.momentum import RSIIndicator
from binance.exceptions import BinanceAPIException, BinanceOrderException
from requests.exceptions import ConnectionError, Timeout
import telegram

# Initialize logging
logging.basicConfig(filename='trading_bot.log', level=logging.INFO, format='%(asctime)s %(message)s')

# Binance API setup
api_key = 'your_api_key'
api_secret = 'your_api_secret'
client = Client(api_key, api_secret)

# Telegram setup for notifications
telegram_bot_token = 'your_telegram_bot_token'
telegram_chat_id = 'your_telegram_chat_id'
telegram_bot = telegram.Bot(token=telegram_bot_token)

# List of coins to trade
coins = [
    'BTC', 'ETH', 'BNB', 'XRP', 'ADA', 'DOGE', 'SOL', 'DOT', 'MATIC', 'LTC',
    'TRX', 'AVAX', 'LINK', 'XLM', 'ATOM', 'ETC', 'XMR', 'BCH', 'ALGO', 'VET',
    'ICP', 'FIL', 'EOS', 'AAVE', 'MKR', 'NEO', 'KSM', 'ZEC', 'SUSHI', 'UNI',
    'YFI', 'GRT', 'CHZ', 'SNX', '1INCH', 'RUNE', 'LRC', 'COMP', 'FTM', 'ENJ'
]
stable_coin = 'USDT'

# Constants for trading strategy
stop_loss_threshold = 0.05  # 5% below purchase price
take_profit_threshold = 0.10  # 10% above purchase price

def send_telegram_message(message):
    try:
        telegram_bot.send_message(chat_id=telegram_chat_id, text=message)
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")

def get_historical_data(symbol, interval='1h', limit=100):
    retries = 5
    for i in range(retries):
        try:
            klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
            df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 
                                               'quote_av', 'trades', 'tb_base_av', 'tb_quote_av', 'ignore'])
            df['close'] = df['close'].astype(float)
            return df
        except (BinanceAPIException, ConnectionError, Timeout) as e:
            logging.error(f"Exception during fetching historical data for {symbol}: {e}")
            if i < retries - 1:
                time.sleep(2 ** i)  # Exponential backoff
            else:
                send_telegram_message(f"Failed to fetch data for {symbol} after {retries} retries.")
    return pd.DataFrame()

def calculate_indicators(df):
    df['sma_50'] = SMAIndicator(df['close'], 50).sma_indicator()
    df['sma_200'] = SMAIndicator(df['close'], 200).sma_indicator()
    df['ema_20'] = EMAIndicator(df['close'], 20).ema_indicator()
    df['rsi'] = RSIIndicator(df['close'], 14).rsi()
    macd = MACD(df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    return df

def get_trading_fee():
    try:
        fees = client.get_trade_fee()
        return float(fees['tradeFee'][0]['taker'])  # Assuming a fixed taker fee
    except (BinanceAPIException, ConnectionError, Timeout) as e:
        logging.error(f"Failed to retrieve trading fee: {e}")
        return 0.001  # Default to 0.1% if unable to retrieve

def trading_strategy(symbol):
    df = get_historical_data(symbol)
    if df.empty:
        return None

    df = calculate_indicators(df)

    latest = df.iloc[-1]
    if latest['sma_50'] > latest['sma_200'] and latest['rsi'] < 30 and latest['macd'] > latest['macd_signal']:
        return 'buy'
    elif latest['rsi'] > 70 and latest['macd'] < latest['macd_signal']:
        return 'sell'
    return 'hold'

def execute_trade(from_coin, to_coin):
    from_to_stable = f"{from_coin}{stable_coin}"
    stable_to_to = f"{to_coin}{stable_coin}"
    trading_fee = get_trading_fee()

    amount = get_balance(from_coin)
    if amount == 0:
        logging.info(f"No {from_coin} balance to trade.")
        return False

    from_coin_price = get_price(from_to_stable)
    to_coin_price = get_price(stable_to_to)

    try:
        # Sell from_coin to USDT
        order = client.order_market_sell(symbol=from_to_stable, quantity=amount)
        usdt_received = float(order['fills'][0]['price']) * amount * (1 - trading_fee)

        # Buy to_coin using USDT
        amount_to_buy = usdt_received / to_coin_price
        order = client.order_market_buy(symbol=stable_to_to, quantity=amount_to_buy)
        
        logging.info(f"Traded {from_coin} to {to_coin}, New Amount: {amount_to_buy} {to_coin}")
        send_telegram_message(f"Trade executed: {from_coin} → {to_coin}, Amount: {amount_to_buy}")
        return True

    except BinanceAPIException as e:
        logging.error(f"Binance API exception: {e}")
        send_telegram_message(f"Trade failed: {from_coin} → {to_coin}. Error: {e}")
    except BinanceOrderException as e:
        logging.error(f"Binance order exception: {e}")
        send_telegram_message(f"Order failed: {from_coin} → {to_coin}. Error: {e}")
    return False

def get_balance(asset):
    try:
        balance = client.get_asset_balance(asset=asset)
        return float(balance['free'])
    except BinanceAPIException as e:
        logging.error(f"Binance API exception: {e}")
    return 0

def get_price(symbol):
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except BinanceAPIException as e:
        logging.error(f"Binance API exception: {e}")
    except BinanceOrderException as e:
        logging.error(f"Binance order exception: {e}")

def rebalance_portfolio(target_allocation):
    """Rebalance the portfolio based on predefined allocation percentages."""
    total_usd_value = sum(get_balance(coin) * get_price(f"{coin}{stable_coin}") for coin in coins)
    
    for coin, target_pct in target_allocation.items():
        if coin not in coins:
            continue
        
        current_value = get_balance(coin) * get_price(f"{coin}{stable_coin}")
        current_pct = current_value / total_usd_value

        if current_pct < target_pct:
            amount_to_buy = ((target_pct - current_pct) * total_usd_value) / get_price(f"{coin}{stable_coin}")
            logging.info(f"Rebalancing: Buying more {coin}, Amount: {amount_to_buy}")
            execute_trade(stable_coin, coin)
        elif current_pct > target_pct:
            amount_to_sell = ((current_pct - target_pct) * total_usd_value) / get_price(f"{coin}{stable_coin}")
            logging.info(f"Rebalancing: Selling some {coin}, Amount: {amount_to_sell}")
            execute_trade(coin, stable_coin)

def stop_loss_check(purchase_prices):
    """Check if any holdings have hit stop-loss thresholds."""
    for coin, purchase_price in purchase_prices.items():
        if purchase_price == 0:
            continue
        current_price = get_price(f"{coin}{stable_coin}")
        if (purchase_price - current_price) / purchase_price >= stop_loss_threshold:
            logging.info(f"Stop-loss triggered for {coin}")
            execute_trade(coin, stable_coin)

def take_profit_check(purchase_prices):
    """Check if any holdings have hit take-profit thresholds."""
    for coin, purchase_price in purchase_prices.items():
        if purchase_price == 0:
            continue
        current_price = get_price(f"{coin}{stable_coin}")
        if (current_price - purchase_price) / purchase_price >= take_profit_threshold:
            logging.info(f"Take-profit triggered for {coin}")
            execute_trade(coin, stable_coin)

def main():
    send_telegram_message("Trading bot started.")
    purchase_prices = {coin: get_price(f"{coin}{stable_coin}") for coin in coins}
    target_allocation = {
        'BTC': 0.50,
        'ETH': 0.30,
        # Other coins with smaller percentages...
    }

    while True:
        try:
            for i in range(len(coins)):
                from_coin = coins[i]
                to_coin = coins[(i + 1) % len(coins)]

                if get_balance(from_coin) == 0:
                    logging.info(f"No balance in {from_coin}. Skipping trading.")
                    continue

                symbol = f"{from_coin}{stable_coin}"
                action = trading_strategy(symbol)

                if action == 'buy':
                    if execute_trade(from_coin, to_coin):
                        purchase_prices[to_coin] = get_price(f"{to_coin}{stable_coin}")
                elif action == 'sell':
                    logging.info(f"Holding {from_coin}. Strategy indicates 'sell'.")
                else:
                    logging.info(f"Holding {from_coin}. No trade signals.")

            # Perform portfolio management tasks
            rebalance_portfolio(target_allocation)
            stop_loss_check(purchase_prices)
            take_profit_check(purchase_prices)

            # Wait before the next cycle to respect API rate limits and allow market movement
            time.sleep(60)  # Adjust as needed based on market conditions and rate limits

        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            send_telegram_message(f"Trading bot encountered an unexpected error: {e}")
            time.sleep(300)  # Wait before retrying in case of an unexpected failure

if __name__ == "__main__":
    main()