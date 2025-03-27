import logging

class AnalysisManager:
    def __init__(self, client):
        self.client = client
        self._analysis = client.open('Expense Tracker').worksheet('analysis')
        
    
    # def add_observer(self, observer):
    #     """Add a handler that needs to be notified of sheet changes."""
    #     self._observers.append(observer)
    
    # def set_current_sheet(self, sheet_name):
    #     """Update the current sheet and notify all observers."""
    #     try:
    #         new_sheet = self.client.open('Expense Tracker').worksheet(sheet_name)
    #         self._curr_sheet = new_sheet
    #         # Notify all observers of the sheet change
    #         for observer in self._observers:
    #             observer.on_sheet_changed(new_sheet)
    #         return True
    #     except Exception as e:
    #         logging.error(f"Error setting current sheet: {e}")
    #         return False
    
    @property
    def analysis_sheet(self):
        return self._analysis