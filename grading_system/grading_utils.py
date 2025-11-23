from GradingSystemSimilarity import GradingSystemSimilarity
from GradingSystemLLM import GradingSystemLLM
from GradingSystemDummy import GradingSystemDummy
from utils import get_device

def get_grading_system(method: str):
    """
    Initialize grading system and grade assignment
    """
    if "test-chat" in method:
        coefficient = 0.7
        if "low" in method:
            coefficient = 0.4
        elif "high" in method:
            coefficient = 0.95
        grading_system = GradingSystemDummy(coefficient=coefficient)
    elif method == "similarity":
        device = get_device()
        grading_system = GradingSystemSimilarity(device=device)

    else:
        grading_system = GradingSystemLLM(model_name=method)
    return grading_system
