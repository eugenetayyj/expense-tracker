from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import CallbackContext, ConversationHandler
from datetime import datetime
from handlers.utils import ensure_not_in_conversation, CONFIRM_KEYBOARD


CATEGORY_KEYBOARD = ReplyKeyboardMarkup(
        [["📆 Month", "📁 Category"], [ "🎯 Tags", "⏰ Period"]],
        one_time_keyboard=True,
        resize_keyboard=True,
        input_field_placeholder="Choose from the options below",
)

FILTER_TYPE, FILTER_VALUE, ADD_ANOTHER_FILTER, START_DATE, END_DATE = range(5)

class QueryHandler:
    def __init__(self, sheet_manager):
        self.sheet_manager = sheet_manager

    async def start_query(self, update: Update, context: CallbackContext):
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

    async def get_filter_type(self, update: Update, context: CallbackContext):
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

    async def get_start_date(self, update: Update, context: CallbackContext):
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

    async def get_end_date(self, update: Update, context: CallbackContext):
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

    async def get_filter_value(self, update: Update, context: CallbackContext):
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

    async def add_another_filter(self, update: Update, context: CallbackContext):
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
            records = self.sheet_manager.current_sheet.get_all_records()
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
