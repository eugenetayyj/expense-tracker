from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import CallbackContext
import logging


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

def get_all_categories(categories):
    """Get all categories from the Google Sheet."""
    try:
        # Get all values from the first column
        category_cells = categories.col_values(1)
        return category_cells
    except Exception as e:
        logging.error(f"Error getting categories: {e}")
        return ["Food", "Travel", "Shopping", "Entertainment", "Utilities", "Other"]  # Default fallback