import asyncio
import logging
import os
from telegram.ext import Application
from main import setup_google_sheets, add_expense_handler, query_expenses_handler, handle_categories_handler, CommandHandler, summary, table_expenses_handler, global_cancel

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

async def main():
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
        
        # Add handlers
        application.add_handler(add_expense_handler)
        application.add_handler(query_expenses_handler)
        application.add_handler(handle_categories_handler)
        application.add_handler(CommandHandler("summary", summary))
        application.add_handler(table_expenses_handler)
        application.add_handler(CommandHandler("cancel", global_cancel))
        
        # Start the bot in polling mode
        logger.info("Starting bot in polling mode...")
        await application.run_polling()
        
        logger.info("Bot is running. Press Ctrl+C to stop.")
        # Run the bot until the user presses Ctrl-C
        # await application.idle()
    except Exception as e:
        logger.error(f"Error running bot: {e}")
        # Print more detailed error information
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()