from typing import List
import jsonlines
import torch

def get_device():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def read_rubrics(file_path: str) -> List[dict]:
    """
    Read rubrics from a JSON Lines file.
    
    Args:
        file_path: Path to the JSON Lines file containing rubric items.
        
    Returns:
        A list of dictionaries, each representing a rubric item.
    """
    with jsonlines.open(file_path, 'r') as reader:
        return [item for item in reader]

def format_rubrics(rubric_items: List[dict]) -> str:
    """
    Format the rubric items into a string for better readability.
    
    Args:
        rubric_items: List of dictionaries containing rubric items.
        
    Returns:
        A formatted string representation of the rubric items.
    """
    formatted_rubrics = []
    for i, item in enumerate(rubric_items):
        labels = []
        for label in item['labels']:
            labels.append(f"• {label["label"]} ({int(label["min"])}-{int(label["max"])} points): {label["description"]}")
        labels = "\n".join(labels)
        #formatted_rubrics.append(f"{item['criteria']}: {item['description']}\n{labels}")
        formatted_rubrics.append(f"{i+1}. {item['criteria']}: {item['description']}\n{labels}")
    #return formatted_rubrics
    return "\n".join(formatted_rubrics)
