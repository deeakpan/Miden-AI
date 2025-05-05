import os
import logging
from dotenv import load_dotenv
import telebot
from telebot import types
from groq import Groq
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
from flask import Flask, request

# Initialize Flask app
app = Flask(__name__)

# Load environment variables from .env.local
load_dotenv('.env.local')

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Groq client
api_key = os.getenv('GROQ_API_KEY')
if not api_key:
    raise ValueError("GROQ_API_KEY not found in environment variables")

groq_client = Groq(api_key=api_key)

# Get Telegram bot token
telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
if not telegram_token:
    raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")

# Initialize bot
bot = telebot.TeleBot(telegram_token)

# Store user states
user_states = {}

# Documentation URLs and subcategories
DOC_URLS = {
    'protocol': 'https://0xmiden.github.io/miden-docs/imported/miden-base/src/index.html',
    'vm': 'https://0xmiden.github.io/miden-docs/imported/miden-vm/src/intro/main.html',
    'compiler': 'https://0xmiden.github.io/miden-docs/imported/miden-compiler/src/getting_started.html',
    'node': 'https://0xmiden.github.io/miden-docs/imported/miden-node/src/index.html',
    'client': {
        'main': 'https://0xmiden.github.io/miden-docs/imported/miden-client/src/index.html',
        'subcategories': {
            'installation': {
                'url': 'https://0xmiden.github.io/miden-docs/imported/miden-client/src/install-and-run.html',
                'description': 'Installation'
            },
            'getting_started': {
                'url': 'https://0xmiden.github.io/miden-docs/imported/miden-client/src/get-started/prerequisites.html',
                'description': 'Getting Started',
                'subtopics': [
                    'Create Account',
                    'Peer-to-peer Transfer',
                    'Private Peer-to-peer Transfer'
                ]
            },
            'features': {
                'url': 'https://0xmiden.github.io/miden-docs/imported/miden-client/src/features.html',
                'description': 'Features'
            },
            'design': {
                'url': 'https://0xmiden.github.io/miden-docs/imported/miden-client/src/design.html',
                'description': 'Design'
            },
            'library': {
                'url': 'https://0xmiden.github.io/miden-docs/imported/miden-client/src/library.html',
                'description': 'Library'
            },
            'cli': {
                'url': 'https://0xmiden.github.io/miden-docs/imported/miden-client/src/cli-reference.html',
                'description': 'CLI Reference',
                'subtopics': [
                    'Config'
                ]
            },
            'examples': {
                'url': 'https://0xmiden.github.io/miden-docs/imported/miden-client/src/examples.html',
                'description': 'Examples'
            },
            'api': {
                'url': 'https://0xmiden.github.io/miden-docs/imported/miden-client/src/api-docs.html',
                'description': 'API Documentation'
            }
        }
    },
    'tutorials': {
        'main': 'https://0xmiden.github.io/miden-docs/imported/miden-tutorials/src/index.html',
        'subcategories': {
            'node_setup': {
                'url': 'https://0xmiden.github.io/miden-docs/imported/miden-tutorials/src/miden_node_setup.html',
                'description': 'Miden Node Setup'
            },
            'rust_client': {
                'url': 'https://0xmiden.github.io/miden-docs/imported/miden-tutorials/src/rust-client/about.html',
                'description': 'Rust Client Tutorials',
                'subtopics': [
                    'Creating Accounts and Faucets',
                    'Mint, Consume, and Create Notes',
                    'Deploying a Counter Contract',
                    'Interacting with Public Smart Contracts',
                    'How To Create Notes with Custom Logic',
                    'Foreign Procedure Invocation',
                    'How to Use Unauthenticated Notes',
                    'How to Use Mappings in Miden Assembly'
                ]
            },
            'web_client': {
                'url': 'https://0xmiden.github.io/miden-docs/imported/miden-tutorials/src/web-client/about.html',
                'description': 'Web Client Tutorials',
                'subtopics': [
                    'Creating Accounts and Faucets',
                    'Mint, Consume, and Create Notes'
                ]
            }
        }
    },
    'assembly': 'https://0xmiden.github.io/miden-docs/imported/miden-vm/src/user_docs/assembly/main.html',
    'stdlib': 'https://0xmiden.github.io/miden-docs/imported/miden-vm/src/user_docs/stdlib/main.html'
}

def is_valid_url(url: str, base_url: str) -> bool:
    """Check if URL is valid and belongs to the same documentation."""
    try:
        parsed_url = urlparse(url)
        parsed_base = urlparse(base_url)
        return (
            parsed_url.netloc == parsed_base.netloc and
            parsed_url.path.startswith(parsed_base.path.split('/src/')[0])
        )
    except Exception:
        return False

def extract_code_blocks(soup: BeautifulSoup) -> str:
    """Extract code blocks from the page."""
    code_blocks = []
    for code in soup.find_all('pre'):
        code_blocks.append(code.get_text())
    return '\n\n'.join(code_blocks)

def scrape_webpage(url: str, max_pages: int = 5) -> str:
    """Scrape webpage content and follow relevant links."""
    try:
        visited_urls = set()
        content_parts = []
        urls_to_visit = [(url, 0)]  # (url, depth)
        
        while urls_to_visit and len(visited_urls) < max_pages:
            current_url, depth = urls_to_visit.pop(0)
            
            if current_url in visited_urls:
                continue
                
            visited_urls.add(current_url)
            logger.info(f"Scraping {current_url}")
            
            response = requests.get(current_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove header and footer
            for element in soup.find_all(['header', 'footer']):
                element.decompose()
            
            # Get main content
            main_content = soup.find('main') or soup
            text_content = main_content.get_text(separator=' ', strip=True)
            
            # Extract code blocks
            code_content = extract_code_blocks(main_content)
            
            # Combine content
            page_content = f"Content from {current_url}:\n{text_content}\n\nCode examples:\n{code_content}"
            content_parts.append(page_content)
            
            # Find and add relevant links
            if depth < 2:  # Only follow links up to 2 levels deep
                for link in main_content.find_all('a', href=True):
                    href = link['href']
                    full_url = urljoin(current_url, href)
                    if is_valid_url(full_url, url) and full_url not in visited_urls:
                        urls_to_visit.append((full_url, depth + 1))
        
        return '\n\n'.join(content_parts)
    except Exception as e:
        logger.error(f"Error scraping webpage: {e}")
        raise

def get_ai_response(content: str, question: str, tutorial_info: dict = None) -> tuple:
    """Get AI response from Groq."""
    try:
        # Build a more engaging system prompt
        system_prompt = (
            "You are a Miden development expert and creative thinker. Your role is to help developers "
            "understand and explore the possibilities of building on Miden. When answering questions:\n\n"
            "1. Start with a brief, engaging introduction that shows you understand the developer's goals\n"
            "2. Share practical insights and real-world examples\n"
            "3. Explain concepts in a conversational way, as if you're brainstorming with a fellow developer\n"
            "4. Include specific technical details and code examples when relevant\n"
            "5. Suggest innovative approaches or unique use cases\n"
            "6. End with actionable next steps or resources for further exploration\n\n"
            "Important guidelines:\n"
            "- Only reference official Miden documentation and resources\n"
            "- Don't make up or assume the existence of communities or resources\n"
            "- Keep responses concise and focused\n\n"
            "Remember: You're not just listing documentation - you're helping developers think creatively "
            "about how to build on Miden's unique capabilities."
        )
        
        # Add tutorial context if available
        if tutorial_info:
            if 'subtopics' in tutorial_info:
                system_prompt += f"\n\nFor this specific tutorial section ({tutorial_info['description']}), "
                system_prompt += "focus on practical implementation details and real-world examples. "
                system_prompt += "Available topics include:\n"
                system_prompt += '\n'.join(f"- {topic}" for topic in tutorial_info['subtopics'])
        
        completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": f"Context: {content}\n\nQuestion: {question}"
                }
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.8,  # Slightly increased for more creative responses
            max_tokens=1024,
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Error getting AI response: {e}")
        raise

def create_command_markup():
    """Create the command buttons markup."""
    keyboard = [
        [
        types.InlineKeyboardButton("Protocol", callback_data="cmd_protocol"),
            types.InlineKeyboardButton("VM", callback_data="cmd_vm")
        ],
        [
        types.InlineKeyboardButton("Compiler", callback_data="cmd_compiler"),
            types.InlineKeyboardButton("Node", callback_data="cmd_node")
        ],
        [
        types.InlineKeyboardButton("Client", callback_data="cmd_client"),
            types.InlineKeyboardButton("Tutorials", callback_data="cmd_tutorials")
        ],
        [
        types.InlineKeyboardButton("Assembly", callback_data="cmd_assembly"),
        types.InlineKeyboardButton("STD Library", callback_data="cmd_stdlib")
    ]
    ]
    return types.InlineKeyboardMarkup(keyboard)

def is_private_chat(chat_id):
    """Check if the chat is a private chat."""
    return chat_id > 0

@bot.message_handler(commands=['start'])
def start(message):
    """Handle /start command."""
    welcome_message = (
        "👋 Welcome to the Miden AI Agent!\n\n"
        "Select a command to get started:"
    )
    bot.send_message(message.chat.id, welcome_message, reply_markup=create_command_markup())

@bot.message_handler(commands=['command'])
def show_commands(message):
    """Handle /command command."""
    commands_message = (
        "Available commands:\n"
        "Select a command to get started:"
    )
    bot.send_message(message.chat.id, commands_message, reply_markup=create_command_markup())

@bot.message_handler(commands=['protocol', 'vm', 'compiler', 'node', 'assembly', 'stdlib'])
def handle_doc_command(message):
    """Handle documentation commands."""
    try:
        text = message.text
        command = text.split()[0].replace('/', '')
        question = text.replace(f"/{command}", "").strip()
        
        if not question:
            if is_private_chat(message.chat.id):
                # In private chat, show buttons
                bot.send_message(
                    message.chat.id,
                    f'What would you like to know about {command}? I can help you explore ideas, '
                    f'understand concepts, or dive into specific implementation details.',
                    reply_markup=create_command_markup()
                )
            else:
                # In group chat, show simple text response
                bot.send_message(
                    message.chat.id,
                    f'Please ask your question about {command}. For example:\n'
                    f'/{command} how does it work?\n'
                    f'/{command} what are the main features?'
                )
            return
        
        # Send processing message
        processing_message = bot.send_message(message.chat.id, 'Let me think about that...')
        
        # Get the documentation URL for the topic
        doc_url = DOC_URLS.get(command)
        if not doc_url:
            if is_private_chat(message.chat.id):
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=processing_message.message_id,
                    text=f"I don't have documentation for {command} yet, but I'd be happy to discuss what you're trying to build!",
                    reply_markup=create_command_markup()
                )
            else:
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=processing_message.message_id,
                    text=f"I don't have documentation for {command} yet, but I'd be happy to discuss what you're trying to build!"
                )
            return
        
        # Scrape webpage
        content = scrape_webpage(doc_url)
        
        # Get AI response
        response = get_ai_response(content, question)
        
        # Update processing message with response
        if is_private_chat(message.chat.id):
            # In private chat, include buttons
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=processing_message.message_id,
                text=response,
                reply_markup=create_command_markup()
            )
        else:
            # In group chat, just show response
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=processing_message.message_id,
                text=response
            )
        
    except Exception as e:
        logger.error(f"Error processing {command} command: {e}")
        if is_private_chat(message.chat.id):
            bot.send_message(
                message.chat.id,
                'Sorry, I encountered an error while processing your request. Please try again later.',
                reply_markup=create_command_markup()
            )
        else:
            bot.send_message(
                message.chat.id,
                'Sorry, I encountered an error while processing your request. Please try again later.'
            )

@bot.message_handler(commands=['client'])
def handle_client_command(message):
    """Handle client command."""
    try:
        text = message.text
        parts = text.split(maxsplit=2)
        if len(parts) < 2:
            if is_private_chat(message.chat.id):
                # Show client categories
                keyboard = [
                    [types.InlineKeyboardButton("Installation", callback_data="client_installation")],
                    [types.InlineKeyboardButton("Getting Started", callback_data="client_getting_started")],
                    [types.InlineKeyboardButton("Features", callback_data="client_features")],
                    [types.InlineKeyboardButton("Design", callback_data="client_design")],
                    [types.InlineKeyboardButton("Library", callback_data="client_library")],
                    [types.InlineKeyboardButton("CLI Reference", callback_data="client_cli")],
                    [types.InlineKeyboardButton("Examples", callback_data="client_examples")],
                    [types.InlineKeyboardButton("API Documentation", callback_data="client_api")],
                    [types.InlineKeyboardButton("Back to Commands", callback_data="back_to_commands")]
                ]
                bot.send_message(
                    message.chat.id,
                    "Select a client category:",
                    reply_markup=types.InlineKeyboardMarkup(keyboard)
                )
            else:
                bot.send_message(
                    message.chat.id,
                    "Please specify a client category. For example:\n"
                    "/client installation\n"
                    "/client getting_started\n"
                    "/client features"
                )
            return
        
        subcategory = parts[1]
        question = parts[2] if len(parts) > 2 else ""
        
        if not question:
            if is_private_chat(message.chat.id):
                bot.send_message(
                    message.chat.id,
                    f"What would you like to know about {subcategory}?",
                    reply_markup=types.InlineKeyboardMarkup([[types.InlineKeyboardButton("Back to Commands", callback_data="back_to_commands")]])
                )
            else:
                bot.send_message(
                    message.chat.id,
                    f"Please ask your question about {subcategory}. For example:\n"
                    f"/client {subcategory} how does it work?\n"
                    f"/client {subcategory} what are the main features?"
                )
            return
        
        # Send processing message
        processing_message = bot.send_message(message.chat.id, 'Let me think about that...')
        
        # Get the documentation URL for the subcategory
        client_info = DOC_URLS.get('client', {})
        subcategory_info = client_info.get('subcategories', {}).get(subcategory)
        
        if not subcategory_info:
            if is_private_chat(message.chat.id):
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=processing_message.message_id,
                    text=f"I don't have documentation for {subcategory} yet, but I'd be happy to discuss what you're trying to build!",
                    reply_markup=create_command_markup()
                )
            else:
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=processing_message.message_id,
                    text=f"I don't have documentation for {subcategory} yet, but I'd be happy to discuss what you're trying to build!"
                )
            return
        
        # Scrape webpage
        content = scrape_webpage(subcategory_info['url'])
        
        # Get AI response
        response = get_ai_response(content, question, subcategory_info)
        
        # Update processing message with response
        if is_private_chat(message.chat.id):
            # In private chat, include buttons
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=processing_message.message_id,
                text=response,
                reply_markup=create_command_markup()
            )
        else:
            # In group chat, just show response
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=processing_message.message_id,
                text=response
            )
        
    except Exception as e:
        logger.error(f"Error processing client command: {e}")
        if is_private_chat(message.chat.id):
            bot.send_message(
                message.chat.id,
                'Sorry, I encountered an error while processing your request. Please try again later.',
                reply_markup=create_command_markup()
            )
        else:
            bot.send_message(
                message.chat.id,
                'Sorry, I encountered an error while processing your request. Please try again later.'
            )

@bot.message_handler(commands=['tutorials'])
def handle_tutorial_command(message):
    """Handle tutorials command."""
    try:
        text = message.text
        parts = text.split(maxsplit=2)
        if len(parts) < 2:
            if is_private_chat(message.chat.id):
                # Show tutorial categories
                keyboard = [
                    [types.InlineKeyboardButton("Node Setup", callback_data="tutorials_node_setup")],
                    [types.InlineKeyboardButton("Rust Client", callback_data="tutorials_rust_client")],
                    [types.InlineKeyboardButton("Web Client", callback_data="tutorials_web_client")],
                    [types.InlineKeyboardButton("Back to Commands", callback_data="back_to_commands")]
                ]
                bot.send_message(
                    message.chat.id,
                    "Select a tutorial category:",
                    reply_markup=types.InlineKeyboardMarkup(keyboard)
                )
            else:
                bot.send_message(
                    message.chat.id,
                    "Please specify a tutorial category. For example:\n"
                    "/tutorials node_setup\n"
                    "/tutorials rust_client\n"
                    "/tutorials web_client"
                )
            return
        
        subcategory = parts[1]
        question = parts[2] if len(parts) > 2 else ""
        
        if not question:
            if is_private_chat(message.chat.id):
                bot.send_message(
                    message.chat.id,
                    f"What would you like to know about {subcategory}?",
                    reply_markup=types.InlineKeyboardMarkup([[types.InlineKeyboardButton("Back to Commands", callback_data="back_to_commands")]])
                )
            else:
                bot.send_message(
                    message.chat.id,
                    f"Please ask your question about {subcategory}. For example:\n"
                    f"/tutorials {subcategory} how does it work?\n"
                    f"/tutorials {subcategory} what are the main features?"
                )
            return
        
        # Send processing message
        processing_message = bot.send_message(message.chat.id, 'Let me think about that...')
        
        # Get the documentation URL for the subcategory
        tutorials_info = DOC_URLS.get('tutorials', {})
        subcategory_info = tutorials_info.get('subcategories', {}).get(subcategory)
        
        if not subcategory_info:
            if is_private_chat(message.chat.id):
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=processing_message.message_id,
                    text=f"I don't have documentation for {subcategory} yet, but I'd be happy to discuss what you're trying to build!",
                    reply_markup=create_command_markup()
                )
            else:
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=processing_message.message_id,
                    text=f"I don't have documentation for {subcategory} yet, but I'd be happy to discuss what you're trying to build!"
                )
            return
        
        # Scrape webpage
        content = scrape_webpage(subcategory_info['url'])
        
        # Get AI response
        response = get_ai_response(content, question, subcategory_info)
        
        # Update processing message with response
        if is_private_chat(message.chat.id):
            # In private chat, include buttons
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=processing_message.message_id,
                text=response,
                reply_markup=create_command_markup()
            )
        else:
            # In group chat, just show response
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=processing_message.message_id,
                text=response
            )
        
    except Exception as e:
        logger.error(f"Error processing tutorials command: {e}")
        if is_private_chat(message.chat.id):
            bot.send_message(
                message.chat.id,
                'Sorry, I encountered an error while processing your request. Please try again later.',
                reply_markup=create_command_markup()
            )
        else:
            bot.send_message(
                message.chat.id,
                'Sorry, I encountered an error while processing your request. Please try again later.'
            )

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Handle all other messages."""
    user_id = message.from_user.id
    
    if user_id in user_states:
        # User has selected a command/category, process their question
        state = user_states[user_id]
        command = state['command']
        
        if 'subcategory' in state:
            # Handle subcategory (client or tutorials)
            if command == 'client':
                # Create a fake message with the command and subcategory
                message.text = f"/client {state['subcategory']} {message.text}"
                handle_client_command(message)
            elif command == 'tutorials':
                # Create a fake message with the command and subcategory
                message.text = f"/tutorials {state['subcategory']} {message.text}"
                handle_tutorial_command(message)
        else:
            # Handle regular command
            # Create a fake message with the command
            message.text = f"/{command} {message.text}"
            handle_doc_command(message)
        
        # Clear the state after processing
        del user_states[user_id]
    else:
        # No command selected, show available commands
        if is_private_chat(message.chat.id):
            # In private chat, show buttons
            bot.send_message(
                message.chat.id,
                "Please select a command to get started:",
                reply_markup=create_command_markup()
            )
        else:
            # In group chat, show simple text response
            bot.send_message(
                message.chat.id,
                "Please use one of the available commands:\n"
                "/protocol - Ask about Miden Protocol\n"
                "/vm - Ask about Miden Virtual Machine\n"
                "/compiler - Ask about Miden Compiler\n"
                "/node - Ask about Miden Node\n"
                "/client - Ask about Miden Client\n"
                "/tutorials - Browse Miden Tutorials\n"
                "/assembly - Ask about Miden Assembly\n"
                "/stdlib - Ask about Standard Library"
            )

@bot.callback_query_handler(func=lambda call: call.data.startswith('cmd_'))
def handle_command_callback(call):
    """Handle command button callbacks."""
    bot.answer_callback_query(call.id)
    
    command = call.data.replace('cmd_', '')
    user_id = call.from_user.id
    
    if command == 'client':
        # Show client categories
        keyboard = [
            [types.InlineKeyboardButton("Installation", callback_data="client_installation")],
            [types.InlineKeyboardButton("Getting Started", callback_data="client_getting_started")],
            [types.InlineKeyboardButton("Features", callback_data="client_features")],
            [types.InlineKeyboardButton("Design", callback_data="client_design")],
            [types.InlineKeyboardButton("Library", callback_data="client_library")],
            [types.InlineKeyboardButton("CLI Reference", callback_data="client_cli")],
            [types.InlineKeyboardButton("Examples", callback_data="client_examples")],
            [types.InlineKeyboardButton("API Documentation", callback_data="client_api")],
            [types.InlineKeyboardButton("Back to Commands", callback_data="back_to_commands")]
        ]
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Select a client category:",
            reply_markup=types.InlineKeyboardMarkup(keyboard)
        )
    elif command == 'tutorials':
        # Show tutorial categories
        keyboard = [
            [types.InlineKeyboardButton("Node Setup", callback_data="tutorials_node_setup")],
            [types.InlineKeyboardButton("Rust Client", callback_data="tutorials_rust_client")],
            [types.InlineKeyboardButton("Web Client", callback_data="tutorials_web_client")],
            [types.InlineKeyboardButton("Back to Commands", callback_data="back_to_commands")]
        ]
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Select a tutorial category:",
            reply_markup=types.InlineKeyboardMarkup(keyboard)
        )
    else:
        # For other commands, set the state and ask for question
        user_states[user_id] = {'command': command}
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"What would you like to know about {command}?",
            reply_markup=types.InlineKeyboardMarkup([[types.InlineKeyboardButton("Back to Commands", callback_data="back_to_commands")]])
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith(('client_', 'tutorials_')))
def handle_category_callback(call):
    """Handle category button callbacks."""
    bot.answer_callback_query(call.id)
    
    category = call.data
    user_id = call.from_user.id
    
    if category.startswith('client_'):
        command = 'client'
        subcategory = category.replace('client_', '')
        user_states[user_id] = {'command': command, 'subcategory': subcategory}
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"What would you like to know about {subcategory}?",
            reply_markup=types.InlineKeyboardMarkup([[types.InlineKeyboardButton("Back to Commands", callback_data="back_to_commands")]])
        )
    elif category.startswith('tutorials_'):
        command = 'tutorials'
        subcategory = category.replace('tutorials_', '')
        user_states[user_id] = {'command': command, 'subcategory': subcategory}
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"What would you like to know about {subcategory}?",
            reply_markup=types.InlineKeyboardMarkup([[types.InlineKeyboardButton("Back to Commands", callback_data="back_to_commands")]])
        )

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_commands')
def handle_back_to_commands(call):
    """Handle back to commands button."""
    bot.answer_callback_query(call.id)
    
    user_id = call.from_user.id
    if user_id in user_states:
        del user_states[user_id]
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="Available commands:\nSelect a command to get started:",
        reply_markup=create_command_markup()
    )

# Add webhook route
@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming webhook updates from Telegram."""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    return 'Error', 400

# Add a simple route for Render health check
@app.route('/')
def home():
    return "Bot is running!"

def main():
    """Start the bot."""
    try:
        logger.info("Starting bot...")
        
        # Get the webhook URL from environment variable or use a default
        webhook_url = os.getenv('WEBHOOK_URL', 'https://your-render-app.onrender.com/webhook')
        
        # Remove any existing webhook
        bot.remove_webhook()
        
        # Set the webhook
        bot.set_webhook(url=webhook_url)
        
        logger.info(f"Webhook set to: {webhook_url}")
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise

if __name__ == '__main__':
    main() 