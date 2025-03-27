
class AnalysisManager:
    def __init__(self, client):
        self.client = client
        self._analysis = client.open('Expense Tracker').worksheet('analysis')
    
    @property
    def analysis_sheet(self):
        return self._analysis