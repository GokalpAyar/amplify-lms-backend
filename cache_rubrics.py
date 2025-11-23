import tempfile
import os
import pickle
from typing import List
from pdf2image import convert_from_path
import jsonlines
from pydantic import BaseModel, Field
from utils import read_rubrics, format_rubrics
from llm_utils import image_content, get_model
from domain_information import PROBLEMS, TEXT_PATH

class Rubric(BaseModel):
    name: str = Field(description="Name of the rubric.")
    description: str = Field(description="What this rubrics evaluate in student rationales.")
    high: str = Field(description="The characterisics of student rationales with a high score. This new description must contain domain knowledge from the textbook.")
    medium: str = Field(description="The characterisics of student rationales with a medium score. This new description must contain domain knowledge from the textbook.")
    low: str = Field(description="The characterisics of student rationales with a low score. This new description must contain domain knowledge from the textbook.")
    very_low: str = Field(description="The characterisics of student rationales with a very low score. This new description must contain domain knowledge from the textbook.")

class Rubrics(BaseModel):
    rubrics: List[Rubric] = Field(description="List of rubrics for grading student rationales.")

def get_user_content(problem: dict, page_images: list) -> List[dict]:
    user_content = [{
        "type": "text",
        "text": f"""Please tailor the rubrics to evaluate student written rationales for their choice to the multiple-choice problem by incorporating knowledge needed for the problem. 
I will give you the problem, rubrics, and seven images. The first image is the system diagram of the problem, the second image contains the choices, and the remaining images are textbook pages that may contain knowledge helpful to solve the problem.

Problem: {problem["problem"]}"""}]
    for img in problem["images"]:
        user_content.append(image_content(img))
    for img in page_images:
        user_content.append(image_content(img))
    return user_content

def generate_rubrics(problem: dict,
                     pages: List[int],
                     model_name: str,
                     textbook_path: str) -> List[Rubric]:
    """
    Generate rubrics for a given problem using the provided pages.
    """

    page_images = []
    llm = get_model(model_name).with_structured_output(Rubrics)
    rubric_items = read_rubrics("./rubrics/generic_rubrics.jsonl")
    formatted_rubrics = format_rubrics(rubric_items)
    
    with tempfile.TemporaryDirectory() as path:
        for page in pages:
            page_images.extend(convert_from_path(
                textbook_path,
                thread_count=os.cpu_count() - 1,
                output_folder=path,
                dpi=300,
                fmt="png",
                first_page=page,
                last_page=page,
                paths_only=True
            ))
        user_content = get_user_content(problem, page_images)
     
        user_content[0]["text"] += f"\n\nRubrics:\n{formatted_rubrics}"
        messages = [{
            "role": "user",
            "content": user_content
        }]
        response = llm.invoke(messages)

    return response.rubrics

if __name__ == "__main__":
    rubric_items = read_rubrics("rubrics/generic_rubrics.jsonl")
    for problem_path, problem in PROBLEMS.items():
        print(f"Generating rubrics for {problem_path}...")
        with open(os.path.join("./problems", problem_path, "pages.pkl"), "rb") as f:
            pages = pickle.load(f)
        new_rubrics = generate_rubrics(problem, pages, "gpt-4.1-mini", TEXT_PATH)
        assert len(new_rubrics) == len(rubric_items), "The number of generated rubrics does not match the number of generic rubrics."
        for i, rubric in enumerate(new_rubrics):
            rubric_items[i]["criteria"] = rubric.name + f" ({int(rubric_items[i]['points'])} Points)"
            rubric_items[i]["description"] = rubric.description
            for j in range(len(rubric_items[i]["labels"])):
                if rubric_items[i]["labels"][j]["label"] == "High":
                    rubric_items[i]["labels"][j]["description"] = rubric.high
                elif rubric_items[i]["labels"][j]["label"] == "Medium":
                    rubric_items[i]["labels"][j]["description"] = rubric.medium
                elif rubric_items[i]["labels"][j]["label"] == "Low":
                    rubric_items[i]["labels"][j]["description"] = rubric.low
                elif rubric_items[i]["labels"][j]["label"] == "Very Low":
                    rubric_items[i]["labels"][j]["description"] = rubric.very_low
        with jsonlines.open(os.path.join("./problems", problem_path, "rubrics.jsonl"), 'w') as writer:
            writer.write_all(rubric_items)