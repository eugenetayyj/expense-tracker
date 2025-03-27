import logging
import os
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, CallbackContext
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import json
from handlers.sheet_handler import (
    SHEET_ACTION, NEW_SHEET, CHANGE_SHEET, PICK_SHEET, SheetHandler
)
from handlers.category_handler import (CATEGORY_ACTION, SELECT_CATEGORY, NEW_CATEGORY_NAME, CategoryHandler)
from handlers.expense_handler import (WHEN, CATEGORY, DESCRIPTION, AMOUNT, TAGS, ExpenseHandler)
from handlers.utils import ensure_not_in_conversation, CONFIRM_KEYBOARD, get_all_categories
from handlers.sheet_manager import SheetManager
from handlers.analysis_manager import AnalysisManager
from handlers.summary_handler import SummaryHandler
from handlers.table_handler import (TABLE_TYPE, TableHandler)
from handlers.query_handler import (FILTER_TYPE, FILTER_VALUE, ADD_ANOTHER_FILTER, START_DATE, END_DATE, QueryHandler)


# Set up logging
logging.basicConfig(level=logging.INFO)

load_dotenv()


def setup_google_sheets():
    try:
        scope = [
            'https://spreadsheets.google.com/feeds', 
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/spreadsheets'  # Add this for write access
        ]
        with open('credentials.json', 'r') as f:
            credentials_data = json.loads(f.read())
        
        private_key = os.getenv("CREDENTIALS_PRIVATE_KEY")
        private_key_id = os.getenv("CREDENTIALS_PRIVATE_ID")
        
        if not private_key or not private_key_id:
            raise ValueError("PRIVATE_KEY or PRIVATE_KEY_ID environment variables are missing")
        
        private_key = private_key.replace("\\n", "\n")
        
        credentials_data["private_key"] = private_key
        credentials_data["private_key_id"] = private_key_id
        
        creds = Credentials.from_service_account_info(credentials_data, scopes=scope)

        # Authorize the client
        client = gspread.authorize(creds)
        
        sheet_manager = SheetManager(client)
        analysis_manager = AnalysisManager(client)
        logging.info("Google Sheets setup complete.")
        return sheet_manager, analysis_manager
    except Exception as e:
        logging.error(f"Error setting up Google Sheets: {e}")
        raise

async def global_cancel(update: Update, context: CallbackContext):
    """Cancel any active conversation and reset the bot state."""
    if "in_conversation" in context.user_data:
        context.user_data.clear()
    
    context.user_data["in_conversation"] = False

    await update.message.reply_text("Current task canceled. You can now start a new command.")
    return ConversationHandler.END

def setup_handlers(sheet_manager, analysis_manager):
    
    sheet_handler = SheetHandler(sheet_manager)
    expense_handler = ExpenseHandler(sheet_manager)
    category_handler = CategoryHandler(sheet_manager)
    summary_handler = SummaryHandler(analysis_manager)
    table_handler = TableHandler(analysis_manager)
    query_handler = QueryHandler(sheet_manager)
    
    sheet_convo_handler = ConversationHandler(
        entry_points=[CommandHandler("handlesheets", sheet_handler.start_curr_sheet)],
        states={
            SHEET_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, sheet_handler.handle_sheet_action)],
            NEW_SHEET: [MessageHandler(filters.TEXT & ~filters.COMMAND, sheet_handler.handle_new_sheet)],
            CHANGE_SHEET: [MessageHandler(filters.TEXT & ~filters.COMMAND, sheet_handler.handle_sheet_change)],
            PICK_SHEET: [MessageHandler(filters.TEXT & ~filters.COMMAND, sheet_handler.handle_pick_sheet)],
        },
        fallbacks=[CommandHandler("cancel", global_cancel)],
    )
    
    categories_convo_handler = ConversationHandler(
        entry_points=[CommandHandler("handlecategories", category_handler.start_handle_categories)],
        states={
            CATEGORY_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, category_handler.handle_category_action)],
            SELECT_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, category_handler.handle_category_selection)],
            NEW_CATEGORY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, category_handler.handle_new_category_name)],
        },
        fallbacks=[CommandHandler("cancel", global_cancel)],
    )
    
    expense_convo_handler = ConversationHandler(
        entry_points=[CommandHandler("add", expense_handler.start_add)],
        states={
            WHEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, expense_handler.get_when)],
            CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, expense_handler.get_category)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, expense_handler.get_description)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, expense_handler.get_amount)],
            TAGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, expense_handler.get_tags)],
        },
        fallbacks=[CommandHandler("cancel", global_cancel)],
    )

    summary_command_handler = CommandHandler("summary", summary_handler.summary)
    
    table_convo_handler = ConversationHandler(
        entry_points=[CommandHandler("table", table_handler.start_table)],
        states={
            TABLE_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, table_handler.get_table_type)],
        },
        fallbacks=[CommandHandler("cancel", global_cancel)],
    )
    
    query_convo_handler = ConversationHandler(
        entry_points=[CommandHandler("query", query_handler.start_query)],
        states={
                FILTER_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, query_handler.get_filter_type)],
                START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, query_handler.get_start_date)],
                END_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, query_handler.get_end_date)],
                FILTER_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, query_handler.get_filter_value)],
                ADD_ANOTHER_FILTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, query_handler.add_another_filter)],
            },
            fallbacks=[CommandHandler("cancel", global_cancel)],
    )

    return sheet_convo_handler, categories_convo_handler, expense_convo_handler, summary_command_handler, table_convo_handler, query_convo_handler

# Main bot setup
async def start_web_bot():
    """
    Initialize and start the Telegram bot.
    """
    try:
        logging.info("Starting Google Sheets setup...")
        sheet_manager, analysis_manager = setup_google_sheets()
        logging.info("Google Sheets setup completed.")

        logging.info("Initializing Telegram bot...")
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            logging.error("TELEGRAM_TOKEN is missing!")
            raise ValueError("TELEGRAM_TOKEN is not set.")
        
        application = Application.builder().token(token).build()
        logging.info("Telegram bot initialized successfully.")
        
        sheet_convo_handler, categories_convo_handler, expense_convo_handler, summary_command_handler, table_convo_handler, query_convo_handler = setup_handlers(sheet_manager, analysis_manager)
        
        
        application.add_handler(expense_convo_handler)
        application.add_handler(sheet_convo_handler)
        application.add_handler(summary_command_handler)
        application.add_handler(categories_convo_handler)
        application.add_handler(table_convo_handler)
        application.add_handler(query_convo_handler)
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
        sheet_manager, analysis_manager = setup_google_sheets()
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
        
        sheet_convo_handler, categories_convo_handler, expense_convo_handler, summary_command_handler, table_convo_handler, query_convo_handler = setup_handlers(sheet_manager, analysis_manager)
        
        
        application.add_handler(expense_convo_handler)
        application.add_handler(sheet_convo_handler)
        application.add_handler(summary_command_handler)
        application.add_handler(categories_convo_handler)
        application.add_handler(table_convo_handler)
        application.add_handler(query_convo_handler)
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
