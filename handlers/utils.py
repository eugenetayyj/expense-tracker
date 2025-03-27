from telegram import Update
from telegram.ext import CallbackContext


async def ensure_not_in_conversation(update: Update, context: CallbackContext):
    """Check if a conversation is already active."""
    if context.user_data.get("in_conversation", False):
        await update.message.reply_text("A command is already active. Type /cancel to stop the current task.")
        return False
    return True