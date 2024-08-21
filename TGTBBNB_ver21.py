import time
import logging
import pandas as pd
from binance.client import Client
from ta.trend import SMAIndicator, EMAIndicator, MACD
from ta.momentum import RSIIndicator
from binance.exceptions import BinanceAPIException, BinanceOrderException
from requests.exceptions import ConnectionError, Timeout
import telegram
import signal
import sys
import random

# Setup logging
logging.basicConfig(filename='trading_bot.log', level=logging.INFO, format='%(asctime)s %(message)s')

# Binance and Telegram API setup
api_key = 'your_api_key'
api_secret = 'your_api_secret'
client = Client(api_key, api_secret)

telegram_bot_token = 'your_telegram_bot_token'
telegram_chat_id = 'your_telegram_chat_id'
telegram_bot = telegram.Bot(token=telegram_bot_token)

# Trading parameters
coins = [
    'BTC', 'ETH', 'BNB', 'XRP', 'ADA', 'DOGE', 'SOL', 'DOT', 'MATIC', 'LTC',
    'TRX', 'AVAX', 'LINK', 'XLM', 'ATOM', 'ETC', 'XMR', 'BCH', 'ALGO', 'VET',
    'ICP', 'FIL', 'EOS', 'AAVE', 'MKR', 'NEO', 'KSM', 'ZEC', 'SUSHI', 'UNI',
    'YFI', 'GRT', 'CHZ', 'SNX', '1INCH', 'RUNE', 'LRC', 'COMP', 'FTM', 'ENJ'
]
stable_coin = 'USDT'
stop_loss_threshold = 0.05
take_profit_threshold = 0.10
max_retries = 5

# Utility class for managing Telegram notifications
class TelegramNotifier:
    def __init__(self, bot, chat_id):
        self.bot = bot
        self.chat_id = chat_id

    def send_message(self, message):
        try:
            self.bot.send_message(chat_id=self.chat_id, text=message)
        except Exception as e:
            logging.error(f"Failed to send Telegram message: {e}")

# Utility class for handling Binance API interactions
class BinanceAPI:
    def __init__(self, client):
        self.client = client

    def get_historical_data(self, symbol, interval='1h', limit=100):
        for i in range(max_retries):
            try:
                klines = self.client.get_klines(symbol=symbol, interval=interval, limit=limit)
                df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time',
                                                   'quote_av', 'trades', 'tb_base_av', 'tb_quote_av', 'ignore'])
                df['close'] = df['close'].astype(float)
                return df
            except (BinanceAPIException, ConnectionError, Timeout) as e:
                logging.error(f"Exception during fetching historical data for {symbol}: {e}")
                if i < max_retries - 1:
                    time.sleep(2 ** i + random.random())
                else:
                    telegram_notifier.send_message(f"Failed to fetch data for {symbol} after {max_retries} retries.")
        return pd.DataFrame()

    def get_balance(self, asset):
        try:
            balance = self.client.get_asset_balance(asset=asset)
            return float(balance['free'])
        except BinanceAPIException as e:
            logging.error(f"Binance API exception: {e}")
        return 0

    def get_price(self, symbol):
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except BinanceAPIException as e:
            logging.error(f"Binance API exception: {e}")
        return 0

    def get_trading_fee(self):
        try:
            fees = self.client.get_trade_fee()
            return float(fees['tradeFee'][0]['taker'])
        except (BinanceAPIException, ConnectionError, Timeout) as e:
            logging.error(f"Failed to retrieve trading fee: {e}")
            return 0.001

    def execute_trade(self, from_coin, to_coin):
        from_to_stable = f"{from_coin}{stable_coin}"
        stable_to_to = f"{to_coin}{stable_coin}"
        trading_fee = self.get_trading_fee()

        amount = self.get_balance(from_coin)
        if amount == 0:
            logging.info(f"No {from_coin} balance to trade.")
            return False

        from_coin_price = self.get_price(from_to_stable)
        to_coin_price = self.get_price(stable_to_to)

        try:
            order = self.client.order_market_sell(symbol=from_to_stable, quantity=amount)
            usdt_received = float(order['fills'][0]['price']) * amount * (1 - trading_fee)

            amount_to_buy = usdt_received / to_coin_price
            order = self.client.order_market_buy(symbol=stable_to_to, quantity=amount_to_buy)

            logging.info(f"Traded {from_coin} to {to_coin}, New Amount: {amount_to_buy} {to_coin}")
            telegram_notifier.send_message(f"Trade executed: {from_coin} → {to_coin}, Amount: {amount_to_buy}")
            return True

        except BinanceAPIException as e:
            logging.error(f"Binance API exception: {e}")
            telegram_notifier.send_message(f"Trade failed: {from_coin} → {to_coin}. Error: {e}")
        except BinanceOrderException as e:
            logging.error(f"Binance order exception: {e}")
            telegram_notifier.send_message(f"Order failed: {from_coin} → {to_coin}. Error: {e}")
        return False

# Core Trading Bot
class TradingBot:
    def __init__(self, binance_api, notifier):
        self.binance_api = binance_api
        self.notifier = notifier

    def calculate_indicators(self, df):
        df['sma_50'] = SMAIndicator(df['close'], 50).sma_indicator()
        df['sma_200'] = SMAIndicator(df['close'], 200).sma_indicator()
        df['ema_20'] = EMAIndicator(df['close'], 20).ema_indicator()
        df['rsi'] = RSIIndicator(df['close'], 14).rsi()
        macd = MACD(df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        return df

    def trading_strategy(self, symbol):
        df = self.binance_api.get_historical_data(symbol)
        if df.empty:
            return None

        df = self.calculate_indicators(df)

        latest = df.iloc[-1]
        if latest['sma_50'] > latest['sma_200'] and latest['rsi'] < 30 and latest['macd'] > latest['macd_signal']:
            return 'buy'
        elif latest['rsi'] > 70 and latest['macd'] < latest['macd_signal']:
            return 'sell'
        return 'hold'

    def rebalance_portfolio(self, target_allocation):
        total_usd_value = sum(self.binance_api.get_balance(coin) * self.binance_api.get_price(f"{coin}{stable_coin}") for coin in coins)

        for coin, target_pct in target_allocation.items():
            if coin not in coins:
                continue

            current_value = self.binance_api.get_balance(coin) * self.binance_api.get_price(f"{coin}{stable_coin}")
            current_pct = current_value / total_usd_value

            if current_pct < target_pct:
                logging.info(f"Rebalancing: Buying more {coin}")
                self.binance_api.execute_trade(stable_coin, coin)
            elif current_pct > target_pct:
                logging.info(f"Rebalancing: Selling some {coin}")
                self.binance_api.execute_trade(coin, stable_coin)

    def stop_loss_check(self, purchase_prices):
        for coin, purchase_price in purchase_prices.items():
            if purchase_price == 0:
                continue
            current_price = self.binance_api.get_price(f"{coin}{stable_coin}")
            if (purchase_price - current_price) / purchase_price >= stop_loss_threshold:
                logging.info(f"Stop-loss triggered for {coin}")
                self.binance_api.execute_trade(coin, stable_coin)

    def take_profit_check(self, purchase_prices):
        for coin, purchase_price in purchase_prices.items():
            if purchase_price == 0:
                continue
            current_price = self.binance_api.get_price(f"{coin}{stable_coin}")
            if (current_price - purchase_price) / purchase_price >= take_profit_threshold:
                logging.info(f"Take-profit triggered for {coin}")
                self.binance_api.execute_trade(coin, stable_coin)

# Handling graceful shutdown
def signal_handler(sig, frame):
    print("Gracefully shutting down the bot...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Main function with menu
# Main function with menu
def main():
    print("Welcome to the Trading Bot!")
    print("Please select a mode:")
    print("1. AST (Automated Smart Trading)")
    print("2. AST+ (Automated Smart Trading with ChatGPT)")
    print("3. SST (Semi Smart Trading)")
    print("4. SST+ (Semi Smart Trading with ChatGPT)")

    choice = input("Enter your choice: ")

    binance_api = BinanceAPI(client)
    notifier = TelegramNotifier(telegram_bot, telegram_chat_id)
    bot = TradingBot(binance_api, notifier)

    if choice == '1':
        print("Starting AST...")
        notifier.send_message("Starting AST mode.")
        start_ast(bot)
    elif choice == '2':
        print("Starting AST+...")
        notifier.send_message("Starting AST+ mode.")
        start_ast_plus(bot)
    elif choice == '3':
        print("Starting SST...")
        notifier.send_message("Starting SST mode.")
        start_sst(bot)
    elif choice == '4':
        print("Starting SST+...")
        notifier.send_message("Starting SST+ mode.")
        start_sst_plus(bot)
    else:
        print("Invalid choice. Exiting...")
        sys.exit(1)

def start_ast(bot):
    purchase_prices = {coin: bot.binance_api.get_price(f"{coin}{stable_coin}") for coin in coins}
    target_allocation = {
        'BTC': 0.50,
        'ETH': 0.30,
    }

    while True:
        try:
            for i in range(len(coins)):
                from_coin = coins[i]
                to_coin = coins[(i + 1) % len(coins)]

                if bot.binance_api.get_balance(from_coin) == 0:
                    logging.info(f"No balance in {from_coin}. Skipping trading.")
                    continue

                symbol = f"{from_coin}{stable_coin}"
                action = bot.trading_strategy(symbol)

                if action == 'buy':
                    if bot.binance_api.execute_trade(from_coin, to_coin):
                        purchase_prices[to_coin] = bot.binance_api.get_price(f"{to_coin}{stable_coin}")
                elif action == 'sell':
                    logging.info(f"Holding {from_coin}. Strategy indicates 'sell'.")
                else:
                    logging.info(f"Holding {from_coin}. No trade signals.")

            bot.rebalance_portfolio(target_allocation)
            bot.stop_loss_check(purchase_prices)
            bot.take_profit_check(purchase_prices)

            time.sleep(60)

        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            bot.notifier.send_message(f"Trading bot encountered an unexpected error: {e}")
            time.sleep(300)

def start_ast_plus(bot):
    purchase_prices = {coin: bot.binance_api.get_price(f"{coin}{stable_coin}") for coin in coins}
    target_allocation = {
        'BTC': 0.50,
        'ETH': 0.30,
    }

    while True:
        try:
            for i in range(len(coins)):
                from_coin = coins[i]
                to_coin = coins[(i + 1) % len(coins)]

                if bot.binance_api.get_balance(from_coin) == 0:
                    logging.info(f"No balance in {from_coin}. Skipping trading.")
                    continue

                symbol = f"{from_coin}{stable_coin}"
                action = bot.trading_strategy(symbol)

                if action == 'buy' or action == 'sell':
                    data = {
                        "symbol": symbol,
                        "from_coin": from_coin,
                        "to_coin": to_coin,
                        "action": action,
                        "balance": bot.binance_api.get_balance(from_coin),
                        "price": bot.binance_api.get_price(symbol),
                        "indicators": bot.calculate_indicators(bot.binance_api.get_historical_data(symbol)).iloc[-1].to_dict()
                    }

                    gpt_advice = ask_chatgpt_for_advice(data)

                    logging.info(f"ChatGPT advice: {gpt_advice}")
                    bot.notifier.send_message(f"ChatGPT advice for {from_coin} -> {to_coin}: {gpt_advice}")

                    if gpt_advice.lower() == 'proceed':
                        if bot.binance_api.execute_trade(from_coin, to_coin):
                            purchase_prices[to_coin] = bot.binance_api.get_price(f"{to_coin}{stable_coin}")
                    else:
                        logging.info(f"ChatGPT advised not to proceed with {action} action for {symbol}.")
                        bot.notifier.send_message(f"ChatGPT advised not to proceed with {action} action for {symbol}.")
                else:
                    logging.info(f"Holding {from_coin}. No trade signals.")

            bot.rebalance_portfolio(target_allocation)
            bot.stop_loss_check(purchase_prices)
            bot.take_profit_check(purchase_prices)

            time.sleep(60)

        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            bot.notifier.send_message(f"Trading bot encountered an unexpected error: {e}")
            time.sleep(300)

def ask_chatgpt_for_advice(data):
    try:
        prompt = (
            f"You're an advanced trading assistant. Here is the current trading data:\n\n"
            f"Symbol: {data['symbol']}\n"
            f"From Coin: {data['from_coin']}\n"
            f"To Coin: {data['to_coin']}\n"
            f"Suggested Action: {data['action']}\n"
            f"Current Balance: {data['balance']}\n"
            f"Price: {data['price']}\n"
            f"Technical Indicators: {data['indicators']}\n\n"
            "Based on this information, should the bot proceed with the trade ('proceed') or hold off ('hold off')?"
        )

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant for trading decisions."},
                {"role": "user", "content": prompt}
            ]
        )

        gpt_advice = response['choices'][0]['message']['content'].strip().lower()
        return gpt_advice

    except Exception as e:
        logging.error(f"Error communicating with ChatGPT: {e}")
        return 'hold off'

def start_sst(bot):
    purchase_prices = {coin: bot.binance_api.get_price(f"{coin}{stable_coin}") for coin in coins}
    target_allocation = {
        'BTC': 0.50,
        'ETH': 0.30,
    }

    while True:
        try:
            for i in range(len(coins)):
                from_coin = coins[i]
                to_coin = coins[(i + 1) % len(coins)]

                if bot.binance_api.get_balance(from_coin) == 0:
                    logging.info(f"No balance in {from_coin}. Skipping trading.")
                    continue

                symbol = f"{from_coin}{stable_coin}"
                action = bot.trading_strategy(symbol)

                if action == 'buy' or action == 'sell':
                    logging.info(f"Suggested action: {action} for {symbol}. Waiting for user confirmation.")
                    bot.notifier.send_message(f"Suggested action: {action} for {symbol}. Please confirm the trade.")
                    user_input = input(f"Do you want to proceed with {action} {from_coin} -> {to_coin}? (yes/no): ")

                    if user_input.lower() == 'yes':
                        if bot.binance_api.execute_trade(from_coin, to_coin):
                            purchase_prices[to_coin] = bot.binance_api.get_price(f"{to_coin}{stable_coin}")
                    else:
                        logging.info(f"User declined the trade for {symbol}.")
                        bot.notifier.send_message(f"User declined the trade for {symbol}.")
                else:
                    logging.info(f"Holding {from_coin}. No trade signals.")

            bot.rebalance_portfolio(target_allocation)
            bot.stop_loss_check(purchase_prices)
            bot.take_profit_check(purchase_prices)

            time.sleep(60)

        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            bot.notifier.send_message(f"Trading bot encountered an unexpected error: {e}")
            time.sleep(300)

def start_sst_plus(bot):
    purchase_prices = {coin: bot.binance_api.get_price(f"{coin}{stable_coin}") for coin in coins}
    target_allocation = {
        'BTC': 0.50,
        'ETH': 0.30,
    }

    while True:
        try:
            for i in range(len(coins)):
                from_coin = coins[i]
                to_coin = coins[(i + 1) % len(coins)]

                if bot.binance_api.get_balance(from_coin) == 0:
                    logging.info(f"No balance in {from_coin}. Skipping trading.")
                    continue

                symbol = f"{from_coin}{stable_coin}"
                action = bot.trading_strategy(symbol)

                if action == 'buy' or action == 'sell':
                    data = {
                        "symbol": symbol,
                        "from_coin": from_coin,
                        "to_coin": to_coin,
                        "action": action,
                        "balance": bot.binance_api.get_balance(from_coin),
                        "price": bot.binance_api.get_price(symbol),
                        "indicators": bot.calculate_indicators(bot.binance_api.get_historical_data(symbol)).iloc[-1].to_dict()
                    }

                    gpt_advice = ask_chatgpt_for_advice(data)

                    logging.info(f"ChatGPT advice: {gpt_advice}")
                    bot.notifier.send_message(f"ChatGPT advice for {from_coin} -> {to_coin}: {gpt_advice}")

                    if gpt_advice.lower() == 'proceed':
                        logging.info(f"Suggested action: {action} for {symbol}. Waiting for user confirmation.")
                        bot.notifier.send_message(f"Suggested action: {action} for {symbol}. Please confirm the trade.")
                        user_input = input(f"Do you want to proceed with {action} {from_coin} -> {to_coin}? (yes/no): ")

                        user_input = input(f"Do you want to proceed with {action} {from_coin} -> {to_coin}? (yes/no): ")

                        if user_input.lower() == 'yes':
                            if bot.binance_api.execute_trade(from_coin, to_coin):
                                purchase_prices[to_coin] = bot.binance_api.get_price(f"{to_coin}{stable_coin}")
                        else:
                            logging.info(f"User declined the trade for {symbol}.")
                            bot.notifier.send_message(f"User declined the trade for {symbol}.")
                    else:
                        logging.info(f"ChatGPT advised not to proceed with {action} action for {symbol}.")
                        bot.notifier.send_message(f"ChatGPT advised not to proceed with {action} action for {symbol}.")
                else:
                    logging.info(f"Holding {from_coin}. No trade signals.")

            bot.rebalance_portfolio(target_allocation)
            bot.stop_loss_check(purchase_prices)
            bot.take_profit_check(purchase_prices)

            time.sleep(60)

        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            bot.notifier.send_message(f"Trading bot encountered an unexpected error: {e}")
            time.sleep(300)

if __name__ == "__main__":
    main()