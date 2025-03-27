from handlers.utils import ensure_not_in_conversation
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ConversationHandler, CallbackContext
from datetime import datetime, timedelta
import logging
from .utils import get_all_categories

WHEN, CATEGORY, DESCRIPTION, AMOUNT, TAGS = range(5)
class ExpenseHandler:
    def __init__(self, sheet_manager):
        self.sheet_manager = sheet_manager
        self.client = sheet_manager.client
        self.categories = sheet_manager.categories
        self.curr_sheet = sheet_manager.current_sheet
        # Register as an observer
        sheet_manager.add_observer(self)
    
    def on_sheet_changed(self, new_sheet):
        """Called when the sheet manager updates the current sheet."""
        self.curr_sheet = new_sheet
    
    async def start_add(self, update: Update, context: CallbackContext):
        """Initiate the add expense process."""
        if not await ensure_not_in_conversation(update, context):
            return ConversationHandler.END

        context.user_data["in_conversation"] = True
        reply_keyboard=[["Today", "Yesterday"]]
        await update.message.reply_text(f"You're adding to {self.curr_sheet.title}. When did you spend this? (Select from the options or type in YYYY-MM-DD)", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True))
        return WHEN
    
    async def get_when(self, update: Update, context: CallbackContext):
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
        all_categories = get_all_categories(self.categories)
        
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

    async def get_category(self, update: Update, context: CallbackContext):
        """Handle the 'category' question."""
        context.user_data["category"] = update.message.text.strip().lower()
        await update.message.reply_text("What did you spend on? (e.g., Lunch, Train ticket, etc.)")
        return DESCRIPTION

    async def get_description(self, update: Update, context: CallbackContext):
        """Handle the 'description' question."""
        context.user_data["description"] = update.message.text.strip()
        await update.message.reply_text("How much did you spend? (e.g., $12.50)")
        return AMOUNT

    async def get_amount(self, update: Update, context: CallbackContext):
        """Handle the 'amount' question."""
        try:
            context.user_data["amount"] = float(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("Invalid amount. Please enter a numeric value (e.g., 12.50).")
            return AMOUNT

        await update.message.reply_text("Any tags you would like to add? (Separate by commas or type 'none')")
        return TAGS

    async def get_tags(self, update: Update, context: CallbackContext):
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
            records = self.curr_sheet.get_all_records()
            next_id = len(records) + 1
            self.curr_sheet.append_row([next_id, date, category, description, amount, tags, formatted_date])

            await update.message.reply_text(
                f"Expense added successfully to {self.curr_sheet.title}:\n"
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
