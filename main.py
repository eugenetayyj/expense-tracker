import logging
import os
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, CallbackContext
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import json
from handlers.sheet_handlers import (
    SHEET_ACTION, NEW_SHEET, CHANGE_SHEET, PICK_SHEET, SheetHandlers
    # start_curr_sheet, handle_sheet_action, handle_new_sheet,
    # handle_sheet_change, handle_pick_sheet
)
from handlers.utils import ensure_not_in_conversation


# Set up logging
logging.basicConfig(level=logging.INFO)

load_dotenv()


def setup_google_sheets():
    try:
        # Define the scope for Google Sheets
        scope = [
            'https://spreadsheets.google.com/feeds', 
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/spreadsheets'  # Add this for write access
        ]
        with open('credentials.json', 'r') as f:
            credentials_data = json.loads(f.read())
        
        # Get private key and private key ID from environment variables
        private_key = os.getenv("CREDENTIALS_PRIVATE_KEY")
        private_key_id = os.getenv("CREDENTIALS_PRIVATE_ID")
        
        if not private_key or not private_key_id:
            raise ValueError("PRIVATE_KEY or PRIVATE_KEY_ID environment variables are missing")
        
        # Replace newlines in private key if they were escaped in the env var
        private_key = private_key.replace("\\n", "\n")
        
        # Add the private key and private key ID to the credentials
        credentials_data["private_key"] = private_key
        credentials_data["private_key_id"] = private_key_id
        
        # Create credentials directly from the credentials.json file
        creds = Credentials.from_service_account_info(credentials_data, scopes=scope)

        # Authorize the client
        global curr_sheet, analysis, categories, client
        client = gspread.authorize(creds)
        # Access the worksheets
        categories = client.open('Expense Tracker').worksheet('settings')
        default_sheet = categories.col_values(3)[1]
        curr_sheet = client.open('Expense Tracker').worksheet(default_sheet)
        analysis = client.open('Expense Tracker').worksheet('analysis')

        logging.info("Google Sheets setup complete.")
        return curr_sheet, analysis, categories, client
    except Exception as e:
        logging.error(f"Error setting up Google Sheets: {e}")
        raise

# async def ensure_not_in_conversation(update: Update, context: CallbackContext):
#     """Check if a conversation is already active."""
#     if context.user_data.get("in_conversation", False):
#         await update.message.reply_text("A command is already active. Type /cancel to stop the current task.")
#         return False
#     return True

CONFIRM_KEYBOARD = ReplyKeyboardMarkup(
    [["✅ Yes", "❌ No"]],
    one_time_keyboard=True,
    resize_keyboard=True,
)

# Command: /add
WHEN, CATEGORY, DESCRIPTION, AMOUNT, TAGS = range(5)
TABLE_TYPE = range(1)
CATEGORY_ACTION, SELECT_CATEGORY, NEW_CATEGORY_NAME = range(3)

CATEGORY_MANAGEMENT_KEYBOARD = ReplyKeyboardMarkup(
    [["➕ Add Category", "✏️ Edit  Category", "🗑️ Delete Category"]],
    one_time_keyboard=True,
    resize_keyboard=True,
)
async def start_handle_categories(update: Update, context: CallbackContext):
    """Start the category management process."""
    if not await ensure_not_in_conversation(update, context):
        return ConversationHandler.END

    context.user_data["in_conversation"] = True
    await update.message.reply_text(
        "What would you like to do with categories?",
        reply_markup=CATEGORY_MANAGEMENT_KEYBOARD,
    )
    return CATEGORY_ACTION

async def handle_category_action(update: Update, context: CallbackContext):
    """Handle the selected category action."""
    action = update.message.text.strip()
    
    if action == "➕ Add Category":
        await update.message.reply_text("Please enter the name of the new category:")
        context.user_data["category_action"] = "add"
        return NEW_CATEGORY_NAME
    
    elif action == "✏️ Edit Category" or action == "✏️ Edit  Category" or action == "🗑️ Delete Category":
        # Get all categories from Google Sheets
        all_categories = get_all_categories()
        
        # Create rows of 2 categories each for better display
        category_rows = [all_categories[i:i+2] for i in range(0, len(all_categories), 2)]
        
        category_keyboard = ReplyKeyboardMarkup(
            category_rows,
            one_time_keyboard=True,
            resize_keyboard=True,
        )
        
        if action == "✏️ Edit Category" or action == "✏️ Edit  Category":
            await update.message.reply_text(
                "Which category would you like to edit?",
                reply_markup=category_keyboard,
            )
            context.user_data["category_action"] = "edit"
        else:  # Delete Category
            await update.message.reply_text(
                "Which category would you like to delete?",
                reply_markup=category_keyboard,
            )
            context.user_data["category_action"] = "delete"
        
        return SELECT_CATEGORY
    
    else:
        await update.message.reply_text(
            "Invalid option. Please select from the options below:",
            reply_markup=CATEGORY_MANAGEMENT_KEYBOARD,
        )
        return CATEGORY_ACTION

async def handle_category_selection(update: Update, context: CallbackContext):
    """Handle the selected category for edit or delete."""
    selected_category = update.message.text.strip()
    
    # Store the selected category
    context.user_data["selected_category"] = selected_category
    
    if context.user_data["category_action"] == "edit":
        # For editing, ask for the new name
        await update.message.reply_text(f"Enter the new name for '{selected_category}':")
        return NEW_CATEGORY_NAME
    
    elif context.user_data["category_action"] == "delete":
        # Delete the category using the Google Sheets function
        success, message = delete_category(selected_category)
        await update.message.reply_text(message)
        
        # End the conversation after deletion
        context.user_data.clear()  # Clear all user data
        context.user_data["in_conversation"] = False
        return ConversationHandler.END

async def handle_new_category_name(update: Update, context: CallbackContext):
    """Handle the new category name for add or edit."""
    new_name = update.message.text.strip().capitalize()
    
    if context.user_data["category_action"] == "add":
        # Add the category using the Google Sheets function
        success, message = add_category(new_name)
        await update.message.reply_text(message)
        
        # End the conversation
        context.user_data.clear()  # Clear all user data
        context.user_data["in_conversation"] = False
        return ConversationHandler.END
    
    elif context.user_data["category_action"] == "edit":
        selected_category = context.user_data["selected_category"]
        
        # Update the category using the Google Sheets function
        success, message = update_category(selected_category, new_name)
        await update.message.reply_text(message)
        
        # End the conversation
        context.user_data.clear()  # Clear all user data
        context.user_data["in_conversation"] = False
        return ConversationHandler.END
    
    # If we get here, something went wrong, so end the conversation
    context.user_data.clear()  # Clear all user data
    context.user_data["in_conversation"] = False
    return ConversationHandler.END


# SHEET_MANAGEMENT_KEYBOARD = ReplyKeyboardMarkup(
#     [["Create", "Switch"]],
#     one_time_keyboard=True,
#     resize_keyboard=True,
# )

# SHEET_ACTION, NEW_SHEET, CHANGE_SHEET, PICK_SHEET = range(4)

# async def start_curr_sheet(update: Update, context: CallbackContext):
#     if not await ensure_not_in_conversation(update, context):
#         return ConversationHandler.END

#     context.user_data["in_conversation"] = True
#     await update.message.reply_text(
#         "What would you like to do with sheets?",
#         reply_markup=SHEET_MANAGEMENT_KEYBOARD,
#     )
#     return SHEET_ACTION

# async def handle_sheet_action(update: Update, context: CallbackContext):
#     """Handle the selected category action."""
#     action = update.message.text.strip()
    
#     if action == "Create":
#         await update.message.reply_text("Please enter the name of the new sheet:")
#         # context.user_data["sheet_action"] = "add"
#         return NEW_SHEET
#     elif action == "Switch":
#         # await update.message.reply_text("Which sheet do you want to access?")
#         # context.user_data["sheet_action"] = "switch"
#         return await handle_sheet_change(update, context)
            
# async def handle_sheet_change(update: Update, context: CallbackContext):
#     """Handle sheet change"""
#     all_sheets = [sheet for sheet in get_all_sheets() if sheet not in ["analysis", "settings"]]
#     sheet_rows = [all_sheets[i:i+3] for i in range(0, len(all_sheets), 3)]
#     SHEET_KEYBOARD = ReplyKeyboardMarkup(
#         sheet_rows,
#         one_time_keyboard=True,
#         resize_keyboard=True,
#     )
#     await update.message.reply_text(
#         "Which sheet do you want to access?",
#         reply_markup=SHEET_KEYBOARD,
#     )
#     return PICK_SHEET

# async def handle_pick_sheet(update: Update, context: CallbackContext):
#     """Handle the selected sheet."""
#     try:
#         context.user_data["selected_sheet"] = update.message.text
#         global curr_sheet
#         curr_sheet = client.open('Expense Tracker').worksheet(context.user_data["selected_sheet"])
#         categories.update_cell(2, 3, context.user_data["selected_sheet"])
#         await update.message.reply_text(f"Switched to {context.user_data['selected_sheet']}")
#     except Exception as e:
#         logging.error(f"Error getting sheets: {e}")
#         await update.message.reply_text("Failed to swap sheets. Please try again later.")
#     context.user_data["in_conversation"] = False
#     return ConversationHandler.END

# def get_all_sheets():
#     try:
#         spreadsheet = client.open('Expense Tracker')
#         sheets = spreadsheet.worksheets()
#         return [sheet.title for sheet in sheets]
#     except Exception as e:
#         logging.error(f"Error getting sheets: {e}")
#         return ["expenses"]

# async def handle_new_sheet(update: Update, context: CallbackContext):
#     """Handle the new category name for add or edit."""
#     new_name = update.message.text.strip().capitalize()

#     # if context.user_data["sheet_action"] == "add":
#         # Add the category using the Google Sheets function
#     result, message = add_sheet(new_name)
#     await update.message.reply_text(message)
    
#     context.user_data.clear()  # Clear all user data
#     context.user_data["in_conversation"] = False
#     return ConversationHandler.END
        
# def add_sheet(sheet_name):
#     "Adds a new sheet to the Google Sheets"
#     try:
#         spreadsheets = client.open('Expense Tracker')
#         try:
#             existing_sheet = spreadsheets.worksheet(sheet_name)
#             return False, f"Sheet '{sheet_name}' already exists!"
#         except:
#             new_sheet = spreadsheets.add_worksheet(title=sheet_name, rows=1000, cols=20)
            
#             # Add headers to the new sheet (same as in expenses sheet)
#             headers = ["ID", "Date", "Category", "Description", "Amount", "Tags", "Formated date"]
#             new_sheet.append_row(headers)
#             return True, f'Sheet {sheet_name} created successfully!'
    
#     except Exception as e:
#         logging.error(f"Error adding entry: {e}")
#         return False, "Failed to add entry. Please try again later."



async def start_add(update: Update, context: CallbackContext):
    """Initiate the add expense process."""
    if not await ensure_not_in_conversation(update, context):
        return ConversationHandler.END

    context.user_data["in_conversation"] = True
    reply_keyboard=[["Today", "Yesterday"]]
    await update.message.reply_text("When did you spend this? (Select from the options or type in YYYY-MM-DD)", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True))
    return WHEN

async def start_add_category(update: Update, context: CallbackContext):
    """Initiate add category process"""
    if not await ensure_not_in_conversation(update, context):
        return ConversationHandler.END

    context.user_data["in_conversation"] = True
    await update.message.reply_text("Please enter the name of the new category:")
    return ADD_CATEGORY

async def save_new_category(update: Update, context: CallbackContext):
    """Save the new category"""
    new_category = update.message.text.strip().capitalize()
    
    # Check if category already exists
    existing_categories = ["Food", "Travel", "Shopping", "Entertainment", "Utilities", "Other"] + custom_categories
    
    if new_category in existing_categories:
        await update.message.reply_text(f"Category '{new_category}' already exists!")
    else:
        custom_categories.append(new_category)
        await update.message.reply_text(f"Category '{new_category}' added successfully!")
    
    context.user_data["in_conversation"] = False
    return ConversationHandler.END

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

    # Send category selection keyboard with categories from Google Sheets
    all_categories = get_all_categories()
    
    # Create rows of 3 categories each
    category_rows = [all_categories[i:i+3] for i in range(0, len(all_categories), 3)]
    
    CATEGORY_KEYBOARD = ReplyKeyboardMarkup(
        category_rows,
        one_time_keyboard=True,
        resize_keyboard=True,
    )
    
    await update.message.reply_text(
        "What category of expense is this? (Choose from below):",
        reply_markup=CATEGORY_KEYBOARD,
    )
    return CATEGORY

async def get_category(update: Update, context: CallbackContext):
    """Handle the 'category' question."""
    context.user_data["category"] = update.message.text.strip().lower()
    await update.message.reply_text("What did you spend on? (e.g., Lunch, Train ticket, etc.)")
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
        records = curr_sheet.get_all_records()
        next_id = len(records) + 1
        curr_sheet.append_row([next_id, date, category, description, amount, tags, formatted_date])

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
        records = curr_sheet.get_all_records()
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
    # Clear all user data
    if "in_conversation" in context.user_data:
        context.user_data.clear()
    
    # Explicitly set in_conversation to False
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

handle_categories_handler = ConversationHandler(
    entry_points=[CommandHandler("handlecategories", start_handle_categories)],
    states={
        CATEGORY_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category_action)],
        SELECT_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category_selection)],
        NEW_CATEGORY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_category_name)],
    },
    fallbacks=[CommandHandler("cancel", global_cancel)],
)

# Category CRUD operations
def get_all_categories():
    """Get all categories from the Google Sheet."""
    try:
        # Get all values from the first column
        category_cells = categories.col_values(1)
        return category_cells
    except Exception as e:
        logging.error(f"Error getting categories: {e}")
        return ["Food", "Travel", "Shopping", "Entertainment", "Utilities", "Other"]  # Default fallback

# For the add_category function, modify to handle case insensitivity
def add_category(category_name):
    """Add a new category to the Google Sheet."""
    try:
        # Check if category already exists (case insensitive)
        all_categories = get_all_categories()
        # Convert all categories to lowercase for comparison
        all_categories_lower = [cat.lower() for cat in all_categories]
        
        if category_name.lower() in all_categories_lower:
            return False, f"Category '{category_name}' already exists!"
        
        # Add the new category to the next empty row
        next_row = len(all_categories) + 1
        categories.update_cell(next_row, 1, category_name.lower())
        return True, f"Category '{category_name}' added successfully!"
    except Exception as e:
        logging.error(f"Error adding category: {e}")
        return False, "Failed to add category due to an error."

# For the update_category function, modify for case insensitivity
def update_category(old_name, new_name):
    """Update a category name in the Google Sheet."""
    try:
        # Check if new name already exists (case insensitive)
        all_categories = get_all_categories()
        all_categories_lower = [cat.lower() for cat in all_categories]
        
        if new_name.lower() in all_categories_lower and new_name.lower() != old_name.lower():
            return False, f"Cannot rename to '{new_name}' as it already exists!"
        
        # Find the category to update
        try:
            # Find the exact match in the sheet
            cell = None
            for idx, category in enumerate(all_categories):
                if category.lower() == old_name.lower():
                    cell = categories.cell(idx+1, 1)
                    break
                    
            if cell:
                categories.update_cell(cell.row, 1, new_name)
                return True, f"Category renamed from '{old_name}' to '{new_name}'."
            else:
                return False, f"Category '{old_name}' not found."
        except Exception as e:
            logging.error(f"Error finding category: {e}")
            return False, f"Category '{old_name}' not found."
    except Exception as e:
        logging.error(f"Error updating category: {e}")
        return False, "Failed to update category due to an error."

# For the delete_category function, modify for case insensitivity
def delete_category(category_name):
    """Delete a category from the Google Sheet."""
    try:
        # Define default categories that cannot be deleted
        default_categories = ["food", "travel", "shopping", "entertainment", "utilities", "other"]
        if category_name.lower() in default_categories:
            return False, f"Cannot delete default category '{category_name}'."
        
        # Find and delete the category
        try:
            # Find the category case-insensitively
            all_categories = get_all_categories()
            row_to_delete = None
            
            for idx, category in enumerate(all_categories):
                if category.lower() == category_name.lower():
                    row_to_delete = idx + 1
                    break
                    
            if row_to_delete:
                categories.delete_rows(row_to_delete)
                return True, f"Category '{category_name}' has been deleted."
            else:
                return False, f"Category '{category_name}' not found."
        except Exception as e:
            logging.error(f"Error finding category to delete: {e}")
            return False, f"Category '{category_name}' not found."
    except Exception as e:
        logging.error(f"Error deleting category: {e}")
        return False, "Failed to delete category due to an error."

# Now fix the handle_new_category_name function to properly end the conversation
async def handle_new_category_name(update: Update, context: CallbackContext):
    """Handle the new category name for add or edit."""
    new_name = update.message.text.strip().capitalize()
    
    if context.user_data["category_action"] == "add":
        # Add the category using the Google Sheets function
        success, message = add_category(new_name)
        await update.message.reply_text(message)
        
        # End the conversation
        context.user_data.clear()  # Clear all user data
        context.user_data["in_conversation"] = False
        return ConversationHandler.END
    
    elif context.user_data["category_action"] == "edit":
        selected_category = context.user_data["selected_category"]
        
        # Update the category using the Google Sheets function
        success, message = update_category(selected_category, new_name)
        await update.message.reply_text(message)
        
        # End the conversation
        context.user_data.clear()  # Clear all user data
        context.user_data["in_conversation"] = False
        return ConversationHandler.END
    
    # If we get here, something went wrong, so end the conversation
    context.user_data.clear()  # Clear all user data
    context.user_data["in_conversation"] = False
    return ConversationHandler.END

# Also fix the handle_category_selection function to properly end after deletion
async def handle_category_selection(update: Update, context: CallbackContext):
    """Handle the selected category for edit or delete."""
    selected_category = update.message.text.strip()
    
    # Store the selected category
    context.user_data["selected_category"] = selected_category
    
    if context.user_data["category_action"] == "edit":
        # For editing, ask for the new name
        await update.message.reply_text(f"Enter the new name for '{selected_category}':")
        return NEW_CATEGORY_NAME
    
    elif context.user_data["category_action"] == "delete":
        # Delete the category using the Google Sheets function
        success, message = delete_category(selected_category)
        await update.message.reply_text(message)
        
        # End the conversation after deletion
        context.user_data.clear()  # Clear all user data
        context.user_data["in_conversation"] = False
        return ConversationHandler.END

# Main bot setup
async def start_web_bot():
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
        
        sheet_handlers = SheetHandlers(client, categories, curr_sheet)

        curr_sheet_handler = ConversationHandler(
            entry_points=[CommandHandler("handlesheets", sheet_handlers.start_curr_sheet)],
            states={
                SHEET_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, sheet_handlers.handle_sheet_action)],
                NEW_SHEET: [MessageHandler(filters.TEXT & ~filters.COMMAND, sheet_handlers.handle_new_sheet)],
                CHANGE_SHEET: [MessageHandler(filters.TEXT & ~filters.COMMAND, sheet_handlers.handle_sheet_change)],
                PICK_SHEET: [MessageHandler(filters.TEXT & ~filters.COMMAND, sheet_handlers.handle_pick_sheet)],
            },
            fallbacks=[CommandHandler("cancel", global_cancel)],
        )

        
        # Add your handlers here
        application.add_handler(add_expense_handler)
        application.add_handler(curr_sheet_handler)
        application.add_handler(query_expenses_handler)
        application.add_handler(handle_categories_handler)
        application.add_handler(CommandHandler("summary", summary))
        application.add_handler(table_expenses_handler)
        application.add_handler(CommandHandler("cancel", global_cancel))

        await application.initialize()
        return application
    except Exception as e:
        logging.error(f"Error initializing bot: {e}")
        raise

# polling
def start_poll_bot():
    """Start the bot in polling mode."""
    try:
        # Initialize Google Sheets
        logging.info("Starting Google Sheets setup...")
        setup_google_sheets()
        logging.info("Google Sheets setup completed.")

        # Get token
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            logging.error("TELEGRAM_TOKEN is missing!")
            raise ValueError("TELEGRAM_TOKEN is not set.")
        
        # Build application with polling
        application = (
            Application.builder()
            .token(token)
            .build()
        )
        logging.info("Telegram bot initialized successfully.")
        
        # Add handlers
        application.add_handler(add_expense_handler)
        application.add_handler(curr_sheet_handler)
        application.add_handler(query_expenses_handler)
        application.add_handler(handle_categories_handler)
        application.add_handler(CommandHandler("summary", summary))
        application.add_handler(table_expenses_handler)
        application.add_handler(CommandHandler("cancel", global_cancel))
        
        # Start the bot in polling mode
        logging.info("Starting bot in polling mode...")
        application.run_polling()
        
        logging.info("Bot is running. Press Ctrl+C to stop.")

    except Exception as e:
        logging.error(f"Error initializing bot: {e}")
        raise
    

if __name__ == "__main__":
    start_poll_bot()
