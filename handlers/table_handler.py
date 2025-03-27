import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ConversationHandler, CallbackContext
from handlers.utils import ensure_not_in_conversation
from datetime import datetime

TABLE_TYPE = range(1)

TABLE_KEYBOARD = ReplyKeyboardMarkup(
    [["📆 Expense by Category by Month", "📁 Expenses Trend"], ["🎯 Expenses by Category all time"]],
    one_time_keyboard=True,
    resize_keyboard=True,
    input_field_placeholder="Choose from the options below",
)

class TableHandler:
    def __init__(self, analysis_manager):
        self.analysis_manager = analysis_manager

    async def start_table(self, update: Update, context: CallbackContext):
        """Start the table query process."""
        if not await ensure_not_in_conversation(update, context):
            return ConversationHandler.END

        context.user_data["in_conversation"] = True

        await update.message.reply_text(
            "Which table information are you interested in? (Choose from the options below)",
            reply_markup=TABLE_KEYBOARD,
        )
        return TABLE_TYPE

    async def get_table_type(self, update: Update, context: CallbackContext):
        """Route the user to the correct table data function based on selection."""
        user_input = update.message.text.strip()

        if user_input == "📆 Expense by Category by Month":
            await self.get_expense_by_category(update, context)
        elif user_input == "📁 Expenses Trend":
            await self.get_expenses_trend(update, context)
        elif user_input == "🎯 Expenses by Category all time":
            await self.get_expenses_by_category_all_time(update, context)
        else:
            await update.message.reply_text(
                "Invalid option selected. Please choose from the provided options.",
                reply_markup=TABLE_KEYBOARD,
            )
            return TABLE_TYPE

        # End the conversation after handling the request
        context.user_data["in_conversation"] = False
        return ConversationHandler.END
    
    @staticmethod
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

    async def get_expense_by_category(self, update: Update, context: CallbackContext):
        """Fetch and format the expense by category for the current month."""
        try:
            # Adjust the range for your specific table
            table_data = self.analysis_manager.analysis_sheet.get('J2:K1000')

            if not table_data or len(table_data) < 2:
                await update.message.reply_text("No data available for expenses by category.")
                return

            headers = table_data[0]
            rows = table_data[1:]
            table_text = self.format_table(headers, rows)

            await update.message.reply_text(
                f"Expense by Category for {datetime.now().strftime('%b %Y')}:\n\n{table_text}"
            )
        except Exception as e:
            logging.error(f"Error fetching expense by category: {e}")
            await update.message.reply_text("Failed to fetch the data. Please try again later.")

    async def get_expenses_trend(self, update: Update, context: CallbackContext):
        """Fetch and format the expenses trend data."""
        try:
            table_data = self.analysis_manager.analysis_sheet.get('D2:E1000')

            if not table_data or len(table_data) < 2:
                await update.message.reply_text("No data available for expenses trend.")
                return

            headers = table_data[0]
            rows = table_data[1:]
            table_text = self.format_table(headers, rows)


            await update.message.reply_text(
                f"Expenses Trend:\n\n{table_text}"
            )
        except Exception as e:
            logging.error(f"Error fetching expenses trend: {e}")
            await update.message.reply_text("Failed to fetch the data. Please try again later.")

    async def get_expenses_by_category_all_time(self, update: Update, context: CallbackContext):
        """Fetch and format the all-time expenses by category data."""
        try:
            table_data = self.analysis_manager.analysis_sheet.get('P2:Q1000')

            if not table_data or len(table_data) < 2:
                await update.message.reply_text("No data available for all-time expenses by category.")
                return
            
            headers = table_data[0]
            rows = table_data[1:]
            table_text = self.format_table(headers, rows)


            await update.message.reply_text(
                f"All-Time Expenses by Category:\n\n{table_text}"
            )
        except Exception as e:
            logging.error(f"Error fetching all-time expenses by category: {e}")
            await update.message.reply
