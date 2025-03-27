import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ConversationHandler, CallbackContext
from handlers.utils import ensure_not_in_conversation, get_all_categories

CATEGORY_ACTION, SELECT_CATEGORY, NEW_CATEGORY_NAME = range(3)

CATEGORY_MANAGEMENT_KEYBOARD = ReplyKeyboardMarkup(
    [["➕ Add Category", "✏️ Edit  Category", "🗑️ Delete Category"]],
    one_time_keyboard=True,
    resize_keyboard=True,
)

class CategoryHandler:
    def __init__(self, sheet_manager):
        self.sheet_manager = sheet_manager
        self.client = sheet_manager.client
        self.categories = sheet_manager.categories
        self.curr_sheet = sheet_manager.current_sheet
        
    async def start_handle_categories(self, update: Update, context: CallbackContext):
        """Start the category management process."""
        if not await ensure_not_in_conversation(update, context):
            return ConversationHandler.END

        context.user_data["in_conversation"] = True
        await update.message.reply_text(
            "What would you like to do with categories?",
            reply_markup=CATEGORY_MANAGEMENT_KEYBOARD,
        )
        return CATEGORY_ACTION

    async def handle_category_action(self, update: Update, context: CallbackContext):
        """Handle the selected category action."""
        action = update.message.text.strip()
        
        if action == "➕ Add Category":
            await update.message.reply_text("Please enter the name of the new category:")
            context.user_data["category_action"] = "add"
            return NEW_CATEGORY_NAME
        
        elif action == "✏️ Edit Category" or action == "🗑️ Delete Category":
            # Get all categories from Google Sheets
            all_categories = get_all_categories(self.categories)
            
            # Create rows of 2 categories each for better display
            category_rows = [all_categories[i:i+2] for i in range(0, len(all_categories), 2)]
            
            category_keyboard = ReplyKeyboardMarkup(
                category_rows,
                one_time_keyboard=True,
                resize_keyboard=True,
            )
            
            if action == "✏️ Edit Category":
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

    async def handle_new_category_name(self, update: Update, context: CallbackContext):
        """Handle the new category name for add or edit."""
        new_name = update.message.text.strip().capitalize()
        
        if context.user_data["category_action"] == "add":
            success, message = self.add_category(new_name)
            await update.message.reply_text(message)
            
            # End the conversation
            context.user_data.clear()  # Clear all user data
            context.user_data["in_conversation"] = False
            return ConversationHandler.END
        
        elif context.user_data["category_action"] == "edit":
            selected_category = context.user_data["selected_category"]
            
            # Update the category using the Google Sheets function
            success, message = self.update_category(selected_category, new_name)
            await update.message.reply_text(message)
            
            # End the conversation
            context.user_data.clear()
            context.user_data["in_conversation"] = False
            return ConversationHandler.END
        
        context.user_data.clear()
        context.user_data["in_conversation"] = False
        return ConversationHandler.END

    async def handle_category_selection(self, update: Update, context: CallbackContext):
        """Handle the selected category for edit or delete."""
        selected_category = update.message.text.strip()
        
        context.user_data["selected_category"] = selected_category
        
        if context.user_data["category_action"] == "edit":
            await update.message.reply_text(f"Enter the new name for '{selected_category}':")
            return NEW_CATEGORY_NAME
        
        elif context.user_data["category_action"] == "delete":
            success, message = self.delete_category(selected_category)
            await update.message.reply_text(message)
            
            context.user_data.clear()  # Clear all user data
            context.user_data["in_conversation"] = False
            return ConversationHandler.END

    # For the add_category function, modify to handle case insensitivity
    def add_category(self, category_name):
        """Add a new category to the Google Sheet."""
        try:
            # Check if category already exists (case insensitive)
            all_categories = get_all_categories(self.categories)
            # Convert all categories to lowercase for comparison
            all_categories_lower = [cat.lower() for cat in all_categories]
            
            if category_name.lower() in all_categories_lower:
                return False, f"Category '{category_name}' already exists!"
            
            # Add the new category to the next empty row
            next_row = len(all_categories) + 1
            self.categories.update_cell(next_row, 1, category_name.lower())
            return True, f"Category '{category_name}' added successfully!"
        except Exception as e:
            logging.error(f"Error adding category: {e}")
            return False, "Failed to add category due to an error."

    # For the update_category function, modify for case insensitivity
    def update_category(self, old_name, new_name):
        """Update a category name in the Google Sheet."""
        try:
            # Check if new name already exists (case insensitive)
            all_categories = get_all_categories(self.categories)
            all_categories_lower = [cat.lower() for cat in all_categories]
            
            if new_name.lower() in all_categories_lower and new_name.lower() != old_name.lower():
                return False, f"Cannot rename to '{new_name}' as it already exists!"
            
            # Find the category to update
            try:
                # Find the exact match in the sheet
                cell = None
                for idx, category in enumerate(all_categories):
                    if category.lower() == old_name.lower():
                        cell = self.categories.cell(idx+1, 1)
                        break
                        
                if cell:
                    self.categories.update_cell(cell.row, 1, new_name)
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
    def delete_category(self, category_name):
        """Delete a category from the Google Sheet."""
        try:
            # Define default categories that cannot be deleted
            default_categories = ["food", "travel", "shopping", "entertainment", "utilities", "other"]
            if category_name.lower() in default_categories:
                return False, f"Cannot delete default category '{category_name}'."
            
            # Find and delete the category
            try:
                # Find the category case-insensitively
                all_categories = get_all_categories(self.categories)
                row_to_delete = None
                
                for idx, category in enumerate(all_categories):
                    if category.lower() == category_name.lower():
                        row_to_delete = idx + 1
                        break
                        
                if row_to_delete:
                    self.categories.delete_rows(row_to_delete)
                    return True, f"Category '{category_name}' has been deleted."
                else:
                    return False, f"Category '{category_name}' not found."
            except Exception as e:
                logging.error(f"Error finding category to delete: {e}")
                return False, f"Category '{category_name}' not found."
        except Exception as e:
            logging.error(f"Error deleting category: {e}")
            return False, "Failed to delete category due to an error."
