import logging
import os
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, CallbackContext
import gspread
from google.oauth2.service_account import Credentials
from cryptography.fernet import Fernet
from datetime import datetime, timedelta

# Set up logging
logging.basicConfig(level=logging.INFO)

load_dotenv()

def decrypt_credentials():
    try:
        # Load the decryption key from the environment variable
        key = os.getenv("DECRYPTION_KEY")
        if not key:
            raise ValueError("DECRYPTION_KEY environment variable is missing.")

        # Initialize the Fernet decryption tool
        fernet = Fernet(key.encode())

        # Read the encrypted credentials file
        with open("credentials.json.enc", "rb") as enc_file:
            encrypted_data = enc_file.read()

        # Decrypt the file
        decrypted_data = fernet.decrypt(encrypted_data)

        # Write the decrypted data to a temporary file
        decrypted_path = "decrypted_credentials.json"
        with open(decrypted_path, "wb") as dec_file:
            dec_file.write(decrypted_data)

        print(f"Decrypted credentials.json successfully: {decrypted_path}")
        return decrypted_path
    except Exception as e:
        print(f"Error decrypting credentials.json: {e}")
        raise

# Google Sheets Setup
def setup_google_sheets():
    try:
        # Decrypt credentials and get the path to the decrypted file
        decrypted_credentials_path = decrypt_credentials()

        # Define the scope for Google Sheets
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_file(decrypted_credentials_path, scopes=scope)

        # Authorize the client
        client = gspread.authorize(creds)
        global expenses, analysis
        # Access the worksheets
        expenses = client.open('Expense Tracker').worksheet('expenses')
        analysis = client.open('Expense Tracker').worksheet('analysis')

        logging.info("Google Sheets setup complete.")
        return expenses, analysis
    except Exception as e:
        logging.error(f"Error setting up Google Sheets: {e}")
        raise

ADD_CATEGORY = range(1)

async def start_add_category(update: Update, context: CallbackContext):
    """Initiate add category process"""
    if not await ensure_not_in_conversation(update, context):
        return ConversationHandler.END

    context.user_data["in_conversation"] = True
    await update.message.reply_text("Enter the name of the new category:")
    return ADD_CATEGORY

async def save_new_category(update: Update, context: CallbackContext):
    """Save the new category to Google Sheets"""
    try:
        new_category = update.message.text.strip().lower()
        
        # Check if category already exists
        existing_categories = [row[0].lower() for row in categories_ws.get_all_values()]
        if new_category in existing_categories:
            await update.message.reply_text("⚠️ This category already exists!")
            context.user_data["in_conversation"] = False
            return ConversationHandler.END
            
        # Add new category to the sheet
        categories_ws.append_row([new_category])
        await update.message.reply_text(f"✅ New category '{new_category}' added successfully!")
        
    except Exception as e:
        logging.error(f"Error adding category: {e}")
        await update.message.reply_text("❌ Failed to add category. Please try again later.")
    
    context.user_data["in_conversation"] = False
    return ConversationHandler.END

async def ensure_not_in_conversation(update: Update, context: CallbackContext):
    """Check if a conversation is already active."""
    if context.user_data.get("in_conversation", False):
        await update.message.reply_text("A command is already active. Type /cancel to stop the current task.")
        return False
    return True

CONFIRM_KEYBOARD = ReplyKeyboardMarkup(
    [["✅ Yes", "❌ No"]],
    one_time_keyboard=True,
    resize_keyboard=True,
)

# Command: /add
WHEN, CATEGORY, DESCRIPTION, AMOUNT, TAGS = range(5)

async def start_add(update: Update, context: CallbackContext):
    """Initiate the add expense process."""
    if not await ensure_not_in_conversation(update, context):
        return ConversationHandler.END

    context.user_data["in_conversation"] = True
    reply_keyboard=[["Today", "Yesterday"]]
    await update.message.reply_text("When did you spend this? (Select from the options or type in YYYY-MM-DD)", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True))
    return WHEN

async def get_when(update: Update, context: CallbackContext):
    """Handle the 'when' question."""
    user_input = update.message.text.strip().lower()

    if user_input == "today":
        date = datetime.now().strftime("%Y-%m-%d")
    elif user_input == "yesterday":
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        try:
            date = datetime.strptime(user_input, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            await update.message.reply_text("Invalid date format. Please use YYYY-MM-DD, 'today', or 'yesterday'.")
            return WHEN

    context.user_data["date"] = date

    # Send category selection keyboard
    CATEGORY_KEYBOARD = ReplyKeyboardMarkup(
        [["Food", "Travel", "Shopping"], ["Entertainment", "Utilities", "Other"]],
        one_time_keyboard=True,
        resize_keyboard=True,
    )
    await update.message.reply_text(
        "What category of expense is this? (Choose from below):",
        reply_markup=CATEGORY_KEYBOARD,
    )
    return CATEGORY

async def get_category(update: Update, context: CallbackContext):
    """Handle the 'category' question with dynamic categories"""
    try:
        # Get all categories from the sheet
        categories = [row[0] for row in categories_ws.get_all_values() if row[0].strip()]
        # Add default categories if sheet is empty
        if not categories:
            categories = ["Food", "Travel", "Shopping", "Entertainment", "Utilities", "Other"]
    except Exception as e:
        logging.error(f"Error loading categories: {e}")
        categories = ["Food", "Travel", "Shopping", "Entertainment", "Utilities", "Other"]

    # Create dynamic keyboard
    category_rows = [categories[i:i+3] for i in range(0, len(categories), 3)]
    CATEGORY_KEYBOARD = ReplyKeyboardMarkup(
        category_rows,
        one_time_keyboard=True,
        resize_keyboard=True,
    )
    
    await update.message.reply_text(
        "What category of expense is this? (Choose from below):",
        reply_markup=CATEGORY_KEYBOARD,
    )
    return DESCRIPTION

async def get_description(update: Update, context: CallbackContext):
    """Handle the 'description' question."""
    context.user_data["description"] = update.message.text.strip()
    await update.message.reply_text("How much did you spend? (e.g., $12.50)")
    return AMOUNT

async def get_amount(update: Update, context: CallbackContext):
    """Handle the 'amount' question."""
    try:
        context.user_data["amount"] = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a numeric value (e.g., 12.50).")
        return AMOUNT

    await update.message.reply_text("Any tags you would like to add? (Separate by commas or type 'none')")
    return TAGS

async def get_tags(update: Update, context: CallbackContext):
    """Handle the 'tags' question."""
    tags = update.message.text.strip()
    context.user_data["tags"] = ", ".join(tag.strip().lower() for tag in tags.split(",")) if tags.lower() != "none" else ""

    date = context.user_data["date"]
    category = context.user_data["category"]
    description = context.user_data["description"]
    amount = context.user_data["amount"]
    tags = context.user_data["tags"]
    formatted_date = datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m")

    try:
        records = expenses.get_all_records()
        next_id = len(records) + 1
        expenses.append_row([next_id, date, category, description, amount, tags, formatted_date])

        await update.message.reply_text(
            f"Expense added successfully:\n"
            f"ID: {next_id}\n"
            f"Date: {date}\n"
            f"Category: {category}\n"
            f"Description: {description}\n"
            f"Amount: ${amount:.2f}\n"
            f"Tags: {tags if tags else 'None'}"
        )
    except Exception as e:
        logging.error(f"Error adding entry: {e}")
        await update.message.reply_text("Failed to add entry. Please try again later.")

    context.user_data["in_conversation"] = False
    return ConversationHandler.END

# Command: /query
CATEGORY_KEYBOARD = ReplyKeyboardMarkup(
        [["📆 Month", "📁 Category"], [ "🎯 Tags", "⏰ Period"]],
        one_time_keyboard=True,
        resize_keyboard=True,
        input_field_placeholder="Choose from the options below",
)

FILTER_TYPE, FILTER_VALUE, ADD_ANOTHER_FILTER, START_DATE, END_DATE = range(5)

async def start_query(update: Update, context: CallbackContext):
    """Start the query process."""
    if not await ensure_not_in_conversation(update, context):
        return ConversationHandler.END

    context.user_data["in_conversation"] = True
    context.user_data["filters"] = {}

    await update.message.reply_text(
        "What would you like to query? (Choose from the options below)",
        reply_markup=CATEGORY_KEYBOARD,
    )
    return FILTER_TYPE

async def get_filter_type(update: Update, context: CallbackContext):
    """Get the filter type."""
    filter_type_mapping = {
        "📆 Month": "month",
        "📁 Category": "category",
        "🎯 Tags": "tags",
        "⏰ Period": "period",
    }

    filter_type = filter_type_mapping.get(update.message.text.strip())

    if not filter_type:
        await update.message.reply_text(
            "Invalid selection. Please choose from the options below.",
            reply_markup=CATEGORY_KEYBOARD,
        )
        return FILTER_TYPE

    context.user_data["current_filter_type"] = filter_type

    if filter_type == "month":
        await update.message.reply_text("Enter the month (format: MMM YYYY):")
        return FILTER_VALUE
    elif filter_type == "category":
        await update.message.reply_text("Enter the category:")
        return FILTER_VALUE
    elif filter_type == "tags":
        await update.message.reply_text("Enter the tags:")
        return FILTER_VALUE
    elif filter_type == "period":
        await update.message.reply_text("Enter the start date (format: DD MMM YYYY):")
        return START_DATE

async def get_start_date(update: Update, context: CallbackContext):
    """Get the start date for the time period in DD MMM YYYY format."""
    start_date_text = update.message.text.strip()

    try:
        start_date = datetime.strptime(start_date_text, "%d %b %Y")
        context.user_data["filters"]["start_date"] = start_date
        await update.message.reply_text("Enter the end date (format: DD MMM YYYY):")
        return END_DATE
    except ValueError:
        await update.message.reply_text(
            "Invalid date format. Please use 'DD MMM YYYY' (e.g., 01 Dec 2024)."
        )
        return START_DATE

async def get_end_date(update: Update, context: CallbackContext):
    """Get the end date for the time period in DD MMM YYYY format."""
    end_date_text = update.message.text.strip()

    try:
        end_date = datetime.strptime(end_date_text, "%d %b %Y")
        start_date = context.user_data["filters"]["start_date"]

        if end_date < start_date:
            await update.message.reply_text("End date cannot be earlier than the start date.")
            return END_DATE

        context.user_data["filters"]["end_date"] = end_date
        await update.message.reply_text(
            f"Time period set from {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}.\n"
            "Do you want to add another filter?",
            reply_markup=CONFIRM_KEYBOARD,
        )
        return ADD_ANOTHER_FILTER
    except ValueError:
        await update.message.reply_text(
            "Invalid date format. Please use 'DD MMM YYYY' (e.g., 31 Dec 2024)."
        )
        return END_DATE

async def get_filter_value(update: Update, context: CallbackContext):
    """Get the filter value."""
    filter_type = context.user_data["current_filter_type"]
    filter_value = update.message.text.strip()
    final_filter_value = None  # Initialize final_filter_value

    if filter_type == "month":
        try:
            parsed_date = datetime.strptime(filter_value, "%b %Y")
            final_filter_value = parsed_date.strftime("%Y-%m")
        except ValueError:
            await update.message.reply_text(
                "Invalid month format. Please use 'MMM YYYY' (e.g., Dec 2024)."
            )
            return FILTER_VALUE
    elif filter_type == "category":
        final_filter_value = filter_value  # Save the raw category as the filter
    elif filter_type == "tags":
        final_filter_value = filter_value.lower().strip()  # Normalize the tags
    elif filter_type == "period":
        # For period, we might need to handle start_date and end_date separately
        final_filter_value = filter_value

    # Check if final_filter_value is set
    if final_filter_value is None:
        await update.message.reply_text(
            "Invalid filter value. Please try again."
        )
        return FILTER_VALUE

    # Save the filter
    context.user_data["filters"][filter_type] = final_filter_value

    # Ask if they want to add another filter
    await update.message.reply_text(
        f"Filter '{filter_type}' set to '{final_filter_value}'.\n"
        "Do you want to add another filter?",
        reply_markup=CONFIRM_KEYBOARD,
    )
    return ADD_ANOTHER_FILTER

async def add_another_filter(update: Update, context: CallbackContext):
    """Ask if the user wants to add another filter with Yes/No buttons."""
    user_input = update.message.text.strip().lower()

    yes_responses = ["✅ yes", "yes", "y"]
    no_responses = ["❌ no", "no", "n"]

    if user_input in yes_responses:
        await update.message.reply_text(
            "What would you like to filter by? (Choose from the options below)",
            reply_markup=ReplyKeyboardMarkup(
                [["📆 Month", "📁 Category"], ["🎯 Tags", "⏰ Period"]],
                one_time_keyboard=True,
                resize_keyboard=True,
            ),
        )
        return FILTER_TYPE
    elif user_input in no_responses:
        filters = context.user_data["filters"]
        records = expenses.get_all_records()
        matching_records = records

        for filter_type, filter_value in filters.items():
            if filter_type == "month":
                matching_records = [
                    record for record in matching_records
                    if filter_value in record["Date"][:7]
                ]
            elif filter_type == "category":
                matching_records = [
                    record for record in matching_records
                    if filter_value.lower() == record["Category"].lower()
                ]
            elif filter_type == "tags":
                matching_records = [
                    record for record in matching_records
                    if filter_value.lower() in record["Tags"].lower()
                ]
            elif filter_type == "start_date":
                matching_records = [
                    record for record in matching_records
                    if datetime.strptime(record["Date"], "%Y-%m-%d") >= filter_value
                ]
            elif filter_type == "end_date":
                matching_records = [
                    record for record in matching_records
                    if datetime.strptime(record["Date"], "%Y-%m-%d") <= filter_value
                ]

        # Calculate total and count
        total_amount = sum(float(record["Amount"]) for record in matching_records)
        count = len(matching_records)

        if count > 0:
            await update.message.reply_text(
                f"Found {count} matching records.\n"
                f"Total Amount Spent: **${total_amount:.2f}**",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text("No matching records found.")

        context.user_data["in_conversation"] = False
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "Invalid response. Please choose 'Yes' or 'No' from the options below.",
            reply_markup=CONFIRM_KEYBOARD,
        )
        return ADD_ANOTHER_FILTER

async def global_cancel(update: Update, context: CallbackContext):
    """Cancel any active conversation and reset the bot state."""
    context.user_data.clear()
    context.user_data["in_conversation"] = False

    await update.message.reply_text("Current task canceled. You can now start a new command.")
    return ConversationHandler.END

# /summary command handler
async def summary(update: Update, context: CallbackContext):
    """Provide a summary of expenses for the current month."""
    try:
        selected_month = analysis.cell(3, 2).value
        selected_month_obj = datetime.strptime(selected_month, "%Y-%m")
        formatted_month = selected_month_obj.strftime("%b %Y")
        monthly_expense = analysis.cell(4, 2).value
        avg_daily_expense = analysis.cell(5, 2).value

        # Send the summary as a Telegram message
        response = (
            f"📊 Expense Summary for {formatted_month}\n"
            f"💰 Monthly Expense: {monthly_expense}\n"
            f"📅 Average Daily Expense: {avg_daily_expense}"
        )
        await update.message.reply_text(response, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error fetching summary: {e}")
        await update.message.reply_text("Failed to fetch summary. Please try again later.")
        
# Command: /table
TABLE_TYPE = range(1)

TABLE_KEYBOARD = ReplyKeyboardMarkup(
    [["📆 Expense by Category by Month", "📁 Expenses Trend"], ["🎯 Expenses by Category all time"]],
    one_time_keyboard=True,
    resize_keyboard=True,
    input_field_placeholder="Choose from the options below",
)

async def start_table(update: Update, context: CallbackContext):
    """Start the table query process."""
    if not await ensure_not_in_conversation(update, context):
        return ConversationHandler.END

    context.user_data["in_conversation"] = True

    await update.message.reply_text(
        "Which table information are you interested in? (Choose from the options below)",
        reply_markup=TABLE_KEYBOARD,
    )
    return TABLE_TYPE

async def get_table_type(update: Update, context: CallbackContext):
    """Route the user to the correct table data function based on selection."""
    user_input = update.message.text.strip()

    if user_input == "📆 Expense by Category by Month":
        await get_expense_by_category(update, context)
    elif user_input == "📁 Expenses Trend":
        await get_expenses_trend(update, context)
    elif user_input == "🎯 Expenses by Category all time":
        await get_expenses_by_category_all_time(update, context)
    else:
        await update.message.reply_text(
            "Invalid option selected. Please choose from the provided options.",
            reply_markup=TABLE_KEYBOARD,
        )
        return TABLE_TYPE

    # End the conversation after handling the request
    context.user_data["in_conversation"] = False
    return ConversationHandler.END

def format_table(headers, rows):
    """Format headers and rows into a readable text table with proper alignment."""
    def sanitize(text):
        # Strip spaces and handle non-breaking spaces
        return str(text).replace('\xa0', ' ').strip()

    # Sanitize headers
    headers = [sanitize(header) for header in headers]

    # Determine the maximum width for each column
    max_widths = [len(header) for header in headers]
    for row in rows:
        for i, cell in enumerate(row):
            max_widths[i] = max(max_widths[i], len(sanitize(cell)))

    # Format header row with dynamic widths
    header_row = "".join(f"{header:<{max_widths[i] + 2}}" for i, header in enumerate(headers))
    table_text = header_row + "\n" + "-" * sum(max_widths) + "\n"

    # Process and format each row
    for row in rows:
        formatted_row = "".join(
            f"{sanitize(row[i]):<{max_widths[i] + 2}}" if i < len(row) else f"{'N/A':<{max_widths[i] + 2}}"
            for i in range(len(headers))
        )
        table_text += formatted_row + "\n"

    return table_text

async def get_expense_by_category(update: Update, context: CallbackContext):
    """Fetch and format the expense by category for the current month."""
    try:
        # Adjust the range for your specific table
        table_data = analysis.get('J2:K1000')

        if not table_data or len(table_data) < 2:
            await update.message.reply_text("No data available for expenses by category.")
            return

        headers = table_data[0]
        rows = table_data[1:]
        table_text = format_table(headers, rows)

        await update.message.reply_text(
            f"Expense by Category for {datetime.now().strftime('%b %Y')}:\n\n{table_text}"
        )
    except Exception as e:
        logging.error(f"Error fetching expense by category: {e}")
        await update.message.reply_text("Failed to fetch the data. Please try again later.")

async def get_expenses_trend(update: Update, context: CallbackContext):
    """Fetch and format the expenses trend data."""
    try:
        table_data = analysis.get('D2:E1000')

        if not table_data or len(table_data) < 2:
            await update.message.reply_text("No data available for expenses trend.")
            return

        headers = table_data[0]
        rows = table_data[1:]
        table_text = format_table(headers, rows)


        await update.message.reply_text(
            f"Expenses Trend:\n\n{table_text}"
        )
    except Exception as e:
        logging.error(f"Error fetching expenses trend: {e}")
        await update.message.reply_text("Failed to fetch the data. Please try again later.")

async def get_expenses_by_category_all_time(update: Update, context: CallbackContext):
    """Fetch and format the all-time expenses by category data."""
    try:
        table_data = analysis.get('P2:Q1000')

        if not table_data or len(table_data) < 2:
            await update.message.reply_text("No data available for all-time expenses by category.")
            return
        
        headers = table_data[0]
        rows = table_data[1:]
        table_text = format_table(headers, rows)


        await update.message.reply_text(
            f"All-Time Expenses by Category:\n\n{table_text}"
        )
    except Exception as e:
        logging.error(f"Error fetching all-time expenses by category: {e}")
        await update.message.reply

# Conversation handlers
add_expense_handler = ConversationHandler(
    entry_points=[CommandHandler("add", start_add)],
    states={
        WHEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_when)],
        CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_category)],
        DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_description)],
        AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
        TAGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_tags)],
    },
    fallbacks=[CommandHandler("cancel", global_cancel)],
)

query_expenses_handler = ConversationHandler(
    entry_points=[CommandHandler("query", start_query)],
    states={
        FILTER_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_filter_type)],
        START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_start_date)],
        END_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_end_date)],
        FILTER_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_filter_value)],
        ADD_ANOTHER_FILTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_another_filter)],
    },
    fallbacks=[CommandHandler("cancel", global_cancel)],
)

table_expenses_handler = ConversationHandler(
    entry_points=[CommandHandler("table", start_table)],
    states={
        TABLE_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_table_type)],
    },
    fallbacks=[CommandHandler("cancel", global_cancel)],
)


# Main bot setup
async def start_bot():
    """
    Initialize and start the Telegram bot.
    """
    try:
        logging.info("Starting Google Sheets setup...")
        setup_google_sheets()
        logging.info("Google Sheets setup completed.")

        logging.info("Initializing Telegram bot...")
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            logging.error("TELEGRAM_TOKEN is missing!")
            raise ValueError("TELEGRAM_TOKEN is not set.")
        
        application = Application.builder().token(token).build()
        logging.info("Telegram bot initialized successfully.")
        
        # Add your handlers here
        application.add_handler(add_expense_handler)
        application.add_handler(query_expenses_handler)
        application.add_handler(CommandHandler("summary", summary))
        application.add_handler(table_expenses_handler)
        application.add_handler(CommandHandler("cancel", global_cancel))
        application.add_handler(ConversationHandler(
        entry_points=[CommandHandler("addcategory", start_add_category)],
        states={
            ADD_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_category)]
        },
        fallbacks=[CommandHandler("cancel", global_cancel)]
    ))

        await application.initialize()
        return application
    except Exception as e:
        logging.error(f"Error initializing bot: {e}")
        raise