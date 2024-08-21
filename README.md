🚀 TGTBBNB - Binance Trade Bot for Telegram

TGTBBNB is an advanced automated trading system designed to operate on the Binance cryptocurrency exchange. Utilizing technical indicators and sophisticated algorithms, it aims to optimize trade decisions in real-time. This bot supports various trading strategies tailored to diverse market conditions, integrates seamlessly with Telegram for real-time notifications, and offers both fully automated and semi-automated trading modes.

✨ Features

	•	📊 Multi-Strategy Trading: Supports multiple trading strategies based on technical analysis, including moving averages, RSI, and MACD.
	•	📲 Telegram Integration: Receive real-time notifications and control the bot through Telegram.
	•	🔧 Error Handling: Robust error handling to manage and retry failed operations, ensuring continuous operation.
	•	🔄 Dynamic Portfolio Rebalancing: Automatically adjusts the portfolio to maintain desired asset allocations.
	•	📝 Logging: Detailed logging for tracking bot activity and diagnosing issues.

📚 Prerequisites

Before you start using the Crypto Trade Bot, you will need:

	•	Python 3.8 or higher
	•	Binance account with API keys
	•	Telegram Bot Token and Chat ID

🛠 Installation

Follow these steps to set up the Crypto Trade Bot:

	1.	Clone the Repository:
	git clone https://github.com/yourgithubusername/crypto-trade-bot.git
	cd crypto-trade-bot

	2.	Install Dependencies:
	pip install -r requirements.txt

	3.	Set up Configuration:
		•	Create a .env file in the root directory.
		•	Add your Binance API keys, Telegram Bot Token, and Chat ID to the .env file:

		BINANCE_API_KEY=your_binance_api_key
		BINANCE_API_SECRET=your_binance_api_secret
		TELEGRAM_BOT_TOKEN=your_telegram_bot_token
		TELEGRAM_CHAT_ID=your_telegram_chat_id

🎮 Usage

To start the bot, run the following command in the terminal:
	python trading_bot.py

Upon launch, the bot will present you with a menu to select the trading mode:

	•	🌟 AST (Automated Smart Trading): Fully automated trading based on predefined strategies.
	•	✨ AST+ (Automated Smart Trading with ChatGPT): Integrates trading decisions advised by ChatGPT for enhanced decision-making.
	•	🖥 SST (Semi Smart Trading): Semi-automated mode that requires user confirmation for trades.
	•	🔍 SST+ (Semi Smart Trading with ChatGPT): Combines semi-automated trading with ChatGPT recommendations, requiring user confirmation.

Choose the desired mode by entering the corresponding number. The bot will proceed with trading based on your selection and provide real-time updates and alerts through Telegram.

🤝 Contributing

Contributions are welcome! Please feel free to fork the repository, make your changes, and submit a pull request.

📜 License

Distributed under the MIT License. See LICENSE for more information.
