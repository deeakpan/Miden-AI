import os
import logging
from dotenv import load_dotenv
import telebot
from telebot import types
import groq
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

groq_client = groq.Groq(api_key=api_key)

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
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("Protocol", callback_data="cmd_protocol"),
        types.InlineKeyboardButton("VM", callback_data="cmd_vm"),
        types.InlineKeyboardButton("Compiler", callback_data="cmd_compiler"),
        types.InlineKeyboardButton("Node", callback_data="cmd_node"),
        types.InlineKeyboardButton("Client", callback_data="cmd_client"),
        types.InlineKeyboardButton("Tutorials", callback_data="cmd_tutorials"),
        types.InlineKeyboardButton("Assembly", callback_data="cmd_assembly"),
        types.InlineKeyboardButton("STD Library", callback_data="cmd_stdlib")
    ]
    markup.add(*buttons)
    return markup

def is_private_chat(chat_id):
    """Check if the chat is a private chat."""
    return chat_id > 0

def handle_doc_command(message, topic):
    """Handle documentation commands."""
    try:
        text = message.text
        # Remove the command from the text
        question = text.replace(f"/{topic}", "").strip()
        
        if not question:
            if is_private_chat(message.chat.id):
                # In private chat, show buttons
                bot.reply_to(
                    message,
                    f'What would you like to know about {topic}? I can help you explore ideas, '
                    f'understand concepts, or dive into specific implementation details.',
                    reply_markup=create_command_markup()
                )
            else:
                # In group chat, show simple text response
                bot.reply_to(
                    message,
                    f'Please ask your question about {topic}. For example:\n'
                    f'/{topic} how does it work?\n'
                    f'/{topic} what are the main features?'
                )
            return
        
        # Send processing message
        processing_message = bot.reply_to(message, 'Let me think about that...')
        
        # Get the documentation URL for the topic
        doc_url = DOC_URLS.get(topic)
        if not doc_url:
            if is_private_chat(message.chat.id):
                bot.edit_message_text(
                    chat_id=processing_message.chat.id,
                    message_id=processing_message.message_id,
                    text=f"I don't have documentation for {topic} yet, but I'd be happy to discuss what you're trying to build!",
                    reply_markup=create_command_markup()
                )
            else:
                bot.edit_message_text(
                    chat_id=processing_message.chat.id,
                    message_id=processing_message.message_id,
                    text=f"I don't have documentation for {topic} yet, but I'd be happy to discuss what you're trying to build!"
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
                chat_id=processing_message.chat.id,
                message_id=processing_message.message_id,
                text=response,
                reply_markup=create_command_markup()
            )
        else:
            # In group chat, just show response
            bot.edit_message_text(
                chat_id=processing_message.chat.id,
                message_id=processing_message.message_id,
                text=response
            )
        
    except Exception as e:
        logger.error(f"Error processing {topic} command: {e}")
        if is_private_chat(message.chat.id):
            bot.reply_to(
                message,
                'Sorry, I encountered an error while processing your request. Please try again later.',
                reply_markup=create_command_markup()
            )
        else:
            bot.reply_to(
                message,
                'Sorry, I encountered an error while processing your request. Please try again later.'
            )

# Register command handlers
@bot.message_handler(commands=['protocol'])
def protocol_command(message):
    handle_doc_command(message, 'protocol')

@bot.message_handler(commands=['vm'])
def vm_command(message):
    handle_doc_command(message, 'vm')

@bot.message_handler(commands=['compiler'])
def compiler_command(message):
    handle_doc_command(message, 'compiler')

@bot.message_handler(commands=['node'])
def node_command(message):
    handle_doc_command(message, 'node')

@bot.message_handler(commands=['client'])
def client_command(message):
    handle_client_command(message)

@bot.message_handler(commands=['tutorials'])
def tutorials_command(message):
    handle_tutorial_command(message)

@bot.message_handler(commands=['assembly'])
def assembly_command(message):
    handle_doc_command(message, 'assembly')

@bot.message_handler(commands=['stdlib'])
def stdlib_command(message):
    handle_doc_command(message, 'stdlib')

# Add regex pattern handlers for subcategory commands
@bot.message_handler(regexp=r'^/client\s+(\w+)\s+(.+)$')
def client_subcategory_command(message):
    # Extract category and question from the message
    match = re.match(r'^/client\s+(\w+)\s+(.+)$', message.text)
    if match:
        category, question = match.groups()
        # Create a new message with the extracted parts
        new_message = message
        new_message.text = f"/client {category} {question}"
        handle_client_command(new_message, category)

@bot.message_handler(regexp=r'^/tutorials\s+(\w+)\s+(.+)$')
def tutorials_subcategory_command(message):
    # Extract category and question from the message
    match = re.match(r'^/tutorials\s+(\w+)\s+(.+)$', message.text)
    if match:
        category, question = match.groups()
        # Create a new message with the extracted parts
        new_message = message
        new_message.text = f"/tutorials {category} {question}"
        handle_tutorial_command(new_message, category)

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
                fake_message = message
                fake_message.text = f"/client {state['subcategory']} {message.text}"
                handle_client_command(fake_message, state['subcategory'])
            elif command == 'tutorials':
                # Create a fake message with the command and subcategory
                fake_message = message
                fake_message.text = f"/tutorials {state['subcategory']} {message.text}"
                handle_tutorial_command(fake_message, state['subcategory'])
        else:
            # Handle regular command
            # Create a fake message with the command
            fake_message = message
            fake_message.text = f"/{command} {message.text}"
            handle_doc_command(fake_message, command)
        
        # Clear the state after processing
        del user_states[user_id]
    else:
        # No command selected, show available commands
        if is_private_chat(message.chat.id):
            # In private chat, show buttons
            markup = types.InlineKeyboardMarkup(row_width=2)
            buttons = [
                types.InlineKeyboardButton("Protocol", callback_data="cmd_protocol"),
                types.InlineKeyboardButton("VM", callback_data="cmd_vm"),
                types.InlineKeyboardButton("Compiler", callback_data="cmd_compiler"),
                types.InlineKeyboardButton("Node", callback_data="cmd_node"),
                types.InlineKeyboardButton("Client", callback_data="cmd_client"),
                types.InlineKeyboardButton("Tutorials", callback_data="cmd_tutorials"),
                types.InlineKeyboardButton("Assembly", callback_data="cmd_assembly"),
                types.InlineKeyboardButton("STD Library", callback_data="cmd_stdlib")
            ]
            markup.add(*buttons)
            bot.reply_to(
                message,
                "Please select a command to get started:",
                reply_markup=markup
            )
        else:
            # In group chat, show simple text response
            bot.reply_to(
                message,
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

def get_tutorial_categories():
    """Get formatted tutorial categories."""
    categories = []
    for key, value in DOC_URLS['tutorials']['subcategories'].items():
        desc = value['description']
        if 'subtopics' in value:
            subtopics = '\n  • ' + '\n  • '.join(value['subtopics'])
            categories.append(f"📚 {desc}{subtopics}")
        else:
            categories.append(f"📚 {desc}")
    return '\n\n'.join(categories)

def handle_tutorial_command(message, category=None):
    """Handle /tutorials command with subcategories."""
    text = message.text.replace('/tutorials', '').strip()
    
    if not text:
        if is_private_chat(message.chat.id):
            # Show tutorial categories with buttons
            markup = types.InlineKeyboardMarkup(row_width=1)
            buttons = [
                types.InlineKeyboardButton("Node Setup", callback_data="tutorials_node_setup"),
                types.InlineKeyboardButton("Rust Client", callback_data="tutorials_rust_client"),
                types.InlineKeyboardButton("Web Client", callback_data="tutorials_web_client"),
                types.InlineKeyboardButton("Back to Commands", callback_data="back_to_commands")
            ]
            markup.add(*buttons)
            bot.reply_to(message, "Select a tutorial category:", reply_markup=markup)
        else:
            # Show simple text response
            response = (
                "Available tutorial categories:\n\n"
                f"{get_tutorial_categories()}\n\n"
                "Example usage:\n"
                "/tutorials rust_client how to create accounts\n"
                "/tutorials web_client mint notes\n"
                "/tutorials node_setup setup guide"
            )
            bot.reply_to(message, response)
        return
    
    # Parse the command to get category and question
    parts = text.split(' ', 1)
    if len(parts) < 2:
        bot.reply_to(
            message,
            "Please provide both the category and your question. For example:\n"
            "/tutorials rust_client how to create accounts",
            reply_markup=create_command_markup() if is_private_chat(message.chat.id) else None
        )
        return
    
    category, question = parts
    category = category.lower()
    
    # Get the appropriate URL based on category
    if category not in DOC_URLS['tutorials']['subcategories']:
        bot.reply_to(
            message,
            f"Unknown tutorial category: {category}\n\n"
            f"Available categories:\n{get_tutorial_categories()}",
            reply_markup=create_command_markup() if is_private_chat(message.chat.id) else None
        )
        return
    
    tutorial_info = DOC_URLS['tutorials']['subcategories'][category]
    url = tutorial_info['url']
    
    # Send processing message
    processing_message = bot.reply_to(message, 'Processing your request...')
    
    try:
        # Scrape webpage
        content = scrape_webpage(url)
        
        # Get AI response with tutorial context
        response = get_ai_response(content, question, tutorial_info)
        
        # Update processing message with response
        if is_private_chat(message.chat.id):
            bot.edit_message_text(
                chat_id=processing_message.chat.id,
                message_id=processing_message.message_id,
                text=response,
                reply_markup=create_command_markup()
            )
        else:
            bot.edit_message_text(
                chat_id=processing_message.chat.id,
                message_id=processing_message.message_id,
                text=response
            )
    except Exception as e:
        logger.error(f"Error processing tutorial command: {e}")
        if is_private_chat(message.chat.id):
            bot.edit_message_text(
                chat_id=processing_message.chat.id,
                message_id=processing_message.message_id,
                text='Sorry, I encountered an error while processing your request. Please try again later.',
                reply_markup=create_command_markup()
            )
        else:
            bot.edit_message_text(
                chat_id=processing_message.chat.id,
                message_id=processing_message.message_id,
                text='Sorry, I encountered an error while processing your request. Please try again later.'
            )

def get_client_categories():
    """Get formatted client categories."""
    categories = []
    for key, value in DOC_URLS['client']['subcategories'].items():
        desc = value['description']
        if 'subtopics' in value:
            subtopics = '\n  • ' + '\n  • '.join(value['subtopics'])
            categories.append(f"📚 {desc}{subtopics}")
        else:
            categories.append(f"📚 {desc}")
    return '\n\n'.join(categories)

def handle_client_command(message, category=None):
    """Handle /client command with subcategories."""
    text = message.text.replace('/client', '').strip()
    
    if not text:
        if is_private_chat(message.chat.id):
            # Show client categories with buttons
            markup = types.InlineKeyboardMarkup(row_width=1)
            buttons = [
                types.InlineKeyboardButton("Installation", callback_data="client_installation"),
                types.InlineKeyboardButton("Getting Started", callback_data="client_getting_started"),
                types.InlineKeyboardButton("Features", callback_data="client_features"),
                types.InlineKeyboardButton("Design", callback_data="client_design"),
                types.InlineKeyboardButton("Library", callback_data="client_library"),
                types.InlineKeyboardButton("CLI Reference", callback_data="client_cli"),
                types.InlineKeyboardButton("Examples", callback_data="client_examples"),
                types.InlineKeyboardButton("API Documentation", callback_data="client_api"),
                types.InlineKeyboardButton("Back to Commands", callback_data="back_to_commands")
            ]
            markup.add(*buttons)
            bot.reply_to(message, "Select a client category:", reply_markup=markup)
        else:
            # Show simple text response
            response = (
                "Available client categories:\n"
                "📚 Installation\n"
                "📚 Getting Started\n"
                "📚 Features\n"
                "📚 Design\n"
                "📚 Library\n"
                "📚 CLI Reference\n"
                "📚 Examples\n"
                "📚 API Documentation\n\n"
                "Example usage:\n"
                "/client installation how to install\n"
                "/client getting_started how to create an account\n"
                "/client cli how to configure"
            )
            bot.reply_to(message, response)
        return
    
    # Parse the command to get category and question
    parts = text.split(' ', 1)
    if len(parts) < 2:
        bot.reply_to(
            message,
            "Please provide both the category and your question. For example:\n"
            "/client installation how to install",
            reply_markup=create_command_markup() if is_private_chat(message.chat.id) else None
        )
        return
    
    category, question = parts
    category = category.lower()
    
    # Get the appropriate URL based on category
    if category not in DOC_URLS['client']['subcategories']:
        bot.reply_to(
            message,
            f"Unknown client category: {category}\n\n"
            "Available categories:\n"
            "📚 Installation\n"
            "📚 Getting Started\n"
            "📚 Features\n"
            "📚 Design\n"
            "📚 Library\n"
            "📚 CLI Reference\n"
            "📚 Examples\n"
            "📚 API Documentation",
            reply_markup=create_command_markup() if is_private_chat(message.chat.id) else None
        )
        return
    
    client_info = DOC_URLS['client']['subcategories'][category]
    url = client_info['url']
    
    # Send processing message
    processing_message = bot.reply_to(message, 'Let me think about that...')
    
    try:
        # Scrape webpage
        content = scrape_webpage(url)
        
        # Get AI response with client context
        response = get_ai_response(content, question, client_info)
        
        # Update processing message with response
        if is_private_chat(message.chat.id):
            bot.edit_message_text(
                chat_id=processing_message.chat.id,
                message_id=processing_message.message_id,
                text=response,
                reply_markup=create_command_markup()
            )
        else:
            bot.edit_message_text(
                chat_id=processing_message.chat.id,
                message_id=processing_message.message_id,
                text=response
            )
    except Exception as e:
        logger.error(f"Error processing client command: {e}")
        if is_private_chat(message.chat.id):
            bot.edit_message_text(
                chat_id=processing_message.chat.id,
                message_id=processing_message.message_id,
                text='Sorry, I encountered an error while processing your request. Please try again later.',
                reply_markup=create_command_markup()
            )
        else:
            bot.edit_message_text(
                chat_id=processing_message.chat.id,
                message_id=processing_message.message_id,
                text='Sorry, I encountered an error while processing your request. Please try again later.'
            )

@bot.message_handler(commands=['start'])
def start(message):
    """Handle /start command."""
    welcome_message = (
        "👋 Welcome to the Miden AI Agent!\n\n"
        "Select a command to get started:"
    )
    bot.reply_to(message, welcome_message, reply_markup=create_command_markup())

@bot.message_handler(commands=['command'])
def show_commands(message):
    """Handle /command command."""
    commands_message = (
        "Available commands:\n"
        "Select a command to get started:"
    )
    bot.reply_to(message, commands_message, reply_markup=create_command_markup())

@bot.callback_query_handler(func=lambda call: call.data.startswith('cmd_'))
def handle_command_callback(call):
    """Handle command button callbacks."""
    command = call.data.replace('cmd_', '')
    user_id = call.from_user.id
    
    if command == 'client':
        # Show client categories
        markup = types.InlineKeyboardMarkup(row_width=1)
        buttons = [
            types.InlineKeyboardButton("Installation", callback_data="client_installation"),
            types.InlineKeyboardButton("Getting Started", callback_data="client_getting_started"),
            types.InlineKeyboardButton("Features", callback_data="client_features"),
            types.InlineKeyboardButton("Design", callback_data="client_design"),
            types.InlineKeyboardButton("Library", callback_data="client_library"),
            types.InlineKeyboardButton("CLI Reference", callback_data="client_cli"),
            types.InlineKeyboardButton("Examples", callback_data="client_examples"),
            types.InlineKeyboardButton("API Documentation", callback_data="client_api"),
            types.InlineKeyboardButton("Back to Commands", callback_data="back_to_commands")
        ]
        markup.add(*buttons)
        bot.edit_message_text(
            "Select a client category:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
    elif command == 'tutorials':
        # Show tutorial categories
        markup = types.InlineKeyboardMarkup(row_width=1)
        buttons = [
            types.InlineKeyboardButton("Node Setup", callback_data="tutorials_node_setup"),
            types.InlineKeyboardButton("Rust Client", callback_data="tutorials_rust_client"),
            types.InlineKeyboardButton("Web Client", callback_data="tutorials_web_client"),
            types.InlineKeyboardButton("Back to Commands", callback_data="back_to_commands")
        ]
        markup.add(*buttons)
        bot.edit_message_text(
            "Select a tutorial category:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
    else:
        # For other commands, set the state and ask for question
        user_states[user_id] = {'command': command}
        bot.send_message(
            call.message.chat.id,
            f"What would you like to know about {command}?",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("Back to Commands", callback_data="back_to_commands")
            )
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith(('client_', 'tutorials_')))
def handle_category_callback(call):
    """Handle category button callbacks."""
    category = call.data
    user_id = call.from_user.id
    
    if category.startswith('client_'):
        command = 'client'
        subcategory = category.replace('client_', '')
        user_states[user_id] = {'command': command, 'subcategory': subcategory}
        bot.send_message(
            call.message.chat.id,
            f"What would you like to know about {subcategory}?",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("Back to Commands", callback_data="back_to_commands")
            )
        )
    elif category.startswith('tutorials_'):
        command = 'tutorials'
        subcategory = category.replace('tutorials_', '')
        user_states[user_id] = {'command': command, 'subcategory': subcategory}
        bot.send_message(
            call.message.chat.id,
            f"What would you like to know about {subcategory}?",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("Back to Commands", callback_data="back_to_commands")
            )
        )

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_commands')
def handle_back_to_commands(call):
    """Handle back to commands button."""
    user_id = call.from_user.id
    if user_id in user_states:
        del user_states[user_id]
    
    bot.edit_message_text(
        "Available commands:\nSelect a command to get started:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=create_command_markup()
    )

def main():
    """Start the bot."""
    try:
        logger.info("Starting bot...")
        
        # Set bot commands for suggestions
        commands = [
            types.BotCommand("start", "Start the Miden AI Agent"),
            types.BotCommand("command", "Show available commands"),
            types.BotCommand("protocol", "Ask about Miden Protocol"),
            types.BotCommand("vm", "Ask about Miden Virtual Machine"),
            types.BotCommand("compiler", "Ask about Miden Compiler"),
            types.BotCommand("node", "Ask about Miden Node"),
            types.BotCommand("client", "Ask about Miden Client"),
            types.BotCommand("tutorials", "Browse Miden Tutorials"),
            types.BotCommand("assembly", "Ask about Miden Assembly"),
            types.BotCommand("stdlib", "Ask about Standard Library")
        ]
        bot.set_my_commands(commands)
        
        # Start polling in a separate thread
        import threading
        polling_thread = threading.Thread(target=bot.infinity_polling)
        polling_thread.start()
        
        # Start Flask app
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port)
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise

if __name__ == '__main__':
    main() 