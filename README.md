# Miden Documentation Bot

A Telegram bot that helps users find answers to their questions about the Miden project by analyzing documentation pages.

## Features

- Web scraping of Miden documentation pages
- AI-powered question answering using Groq
- Clean and user-friendly interface
- Automatic header and footer removal from scraped content

## Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd miden-docs-bot
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Unix or MacOS:
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the project root with your API keys:
```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
GROQ_API_KEY=your_groq_api_key
```

## Running the Bot

1. Make sure your virtual environment is activated
2. Run the bot:
```bash
python bot.py
```

## Usage

1. Start a chat with the bot on Telegram
2. Send the `/start` command to get started
3. Send a Miden documentation URL followed by your question
4. The bot will process the page and provide an answer

Example:
```
https://0xmiden.github.io/miden-docs/index.html
What is Miden?
```

## Error Handling

The bot includes comprehensive error handling for:
- Invalid URLs
- Web scraping failures
- AI response generation issues
- Network connectivity problems

## Contributing

Feel free to submit issues and enhancement requests! 