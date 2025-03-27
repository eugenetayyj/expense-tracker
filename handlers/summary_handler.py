import logging

from telegram import Update
from telegram.ext import CallbackContext
from datetime import datetime


from handlers.utils import ensure_not_in_conversation


class SummaryHandler:
    def __init__(self, analysis_manager):
        self.analysis_manager = analysis_manager
        
    async def summary(self, update: Update, context: CallbackContext):
        """Provide a summary of expenses for the current month."""
        try:
            selected_month = self.analysis_manager.analysis_sheet.cell(3, 2).value
            selected_month_obj = datetime.strptime(selected_month, "%Y-%m")
            formatted_month = selected_month_obj.strftime("%b %Y")
            monthly_expense = self.analysis_manager.analysis_sheet.cell(4, 2).value
            avg_daily_expense = self.analysis_manager.analysis_sheet.cell(5, 2).value

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