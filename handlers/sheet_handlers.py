import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ConversationHandler, CallbackContext
from handlers.utils import ensure_not_in_conversation

SHEET_ACTION, NEW_SHEET, CHANGE_SHEET, PICK_SHEET = range(4)

SHEET_MANAGEMENT_KEYBOARD = ReplyKeyboardMarkup(
    [["Create", "Switch"]],
    one_time_keyboard=True,
    resize_keyboard=True,
)

class SheetHandlers:
    def __init__(self, client, categories, curr_sheet):
        self.client = client
        self.categories = categories
        self.curr_sheet = curr_sheet

    async def start_curr_sheet(self, update: Update, context: CallbackContext):
        if not await ensure_not_in_conversation(update, context):
            return ConversationHandler.END

        context.user_data["in_conversation"] = True
        await update.message.reply_text(
            "What would you like to do with sheets?",
            reply_markup=SHEET_MANAGEMENT_KEYBOARD,
        )
        return SHEET_ACTION

    async def handle_sheet_action(self, update: Update, context: CallbackContext):
        action = update.message.text.strip()
        
        if action == "Create":
            await update.message.reply_text("Please enter the name of the new sheet:")
            return NEW_SHEET
        elif action == "Switch":
            return await self.handle_sheet_change(update, context)

    async def handle_sheet_change(self, update: Update, context: CallbackContext):
        all_sheets = [sheet for sheet in self.get_all_sheets() if sheet not in ["analysis", "settings"]]
        sheet_rows = [all_sheets[i:i+3] for i in range(0, len(all_sheets), 3)]
        SHEET_KEYBOARD = ReplyKeyboardMarkup(
            sheet_rows,
            one_time_keyboard=True,
            resize_keyboard=True,
        )
        await update.message.reply_text(
            "Which sheet do you want to access?",
            reply_markup=SHEET_KEYBOARD,
        )
        return PICK_SHEET

    async def handle_pick_sheet(self, update: Update, context: CallbackContext):
        try:
            context.user_data["selected_sheet"] = update.message.text
            self.curr_sheet = self.client.open('Expense Tracker').worksheet(context.user_data["selected_sheet"])
            self.categories.update_cell(2, 3, context.user_data["selected_sheet"])
            await update.message.reply_text(f"Switched to {context.user_data['selected_sheet']}")
        except Exception as e:
            logging.error(f"Error getting sheets: {e}")
            await update.message.reply_text("Failed to swap sheets. Please try again later.")
        context.user_data["in_conversation"] = False
        return ConversationHandler.END

    async def handle_new_sheet(self, update: Update, context: CallbackContext):
        new_name = update.message.text.strip().capitalize()
        result, message = self.add_sheet(new_name)
        await update.message.reply_text(message)
        
        context.user_data.clear()
        context.user_data["in_conversation"] = False
        return ConversationHandler.END

    def add_sheet(self, sheet_name):
        try:
            spreadsheets = self.client.open('Expense Tracker')
            try:
                existing_sheet = spreadsheets.worksheet(sheet_name)
                return False, f"Sheet '{sheet_name}' already exists!"
            except:
                new_sheet = spreadsheets.add_worksheet(title=sheet_name, rows=1000, cols=20)
                headers = ["ID", "Date", "Category", "Description", "Amount", "Tags", "Formated date"]
                new_sheet.append_row(headers)
                return True, f'Sheet {sheet_name} created successfully!'
        except Exception as e:
            logging.error(f"Error adding entry: {e}")
            return False, "Failed to add entry. Please try again later."

    def get_all_sheets(self):
        try:
            spreadsheet = self.client.open('Expense Tracker')
            sheets = spreadsheet.worksheets()
            return [sheet.title for sheet in sheets]
        except Exception as e:
            logging.error(f"Error getting sheets: {e}")
            return ["expenses"]
    # async def _ensure_not_in_conversation(self, update: Update, context: CallbackContext):
    #     if context.user_data.get("in_conversation", False):
    #         await update.message.reply_text("A command is already active. Type /cancel to stop the current task.")
    #         return False
    #     return True
