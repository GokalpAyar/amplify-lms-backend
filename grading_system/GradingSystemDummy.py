from typing import Dict
from GradingSystem import GradingSystem

class GradingSystemDummy(GradingSystem):
    """
    Main grading system that handles the grading process using semantic similarity
    and grammar checking.
    """
    def __init__(self, coefficient: float):
        super().__init__()
        self.coefficient = coefficient
    
    def _get_score(self, item: Dict, assignment_text: str):
        results = {
            'description': item['description'],
            'max_points': item['points'],
            'justification': "Test justification",
            'score': item['points'] * self.coefficient,
            'word_count': len(assignment_text.split())
        }

        return self._add_labels(item['points'] * self.coefficient, item, results)