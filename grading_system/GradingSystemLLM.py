from typing import Dict
from pydantic import BaseModel, Field
from langchain_openai.chat_models.base import OpenAIRefusalError
from openai import LengthFinishReasonError
from GradingSystem import GradingSystem
from llm_utils import get_model

class Grade(BaseModel):
    """
    Represents a single grade for an assignment.
    """
    justification: str = Field(..., description="Justification for the score")
    score: float = Field(..., description="Score awarded for the assignment")

class GradingSystemLLM(GradingSystem):
    """
    Main grading system that handles the grading process using semantic similarity
    and grammar checking.
    """
    def __init__(self, model_name: str):
        super().__init__()
        llm = get_model(model_name)
        self.llm = llm.with_structured_output(Grade)
    
    def _get_score(self, item: Dict, assignment_text: str):
        critetia_text = item['criteria']
        if item['description'] and item['criteria'] != item['description']:
            critetia_text += f"\n{item['description']}"
        for label in item['labels']:
            critetia_text += f"\n - {label['label']}: {label['description']}"
        messages = [
            ("system", f"You are a grading assistant. Your task is to evaluate the student's assignment based on the following criteria on a scale of 0-{item['points']}:\n{critetia_text}"),
            ("human", assignment_text)
        ]
        try:
            output = self.llm.invoke(messages)
        except (OpenAIRefusalError, LengthFinishReasonError) as e:
            output = Grade(justification=str(e), score=0.0)

        results = {
            'description': item['description'],
            'max_points': item['points'],
            'justification': output.justification,
            'score': output.score,
            'word_count': len(assignment_text.split())
        }

        return self._add_labels(output.score, item, results)