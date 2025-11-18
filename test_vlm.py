import base64
import os
import json
from typing import List
from pydantic import BaseModel, Field
from llm_utils import get_model
from domain_information import PROBLEMS, DOMAIN

class Answer(BaseModel):
    description: str = Field(description="A description of the diagram of the problem.")
    rationale: str = Field(description="A rationale for the given correct answer.")

def image_content(image_path: str) -> List[dict]:
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}

if __name__ == "__main__":
    llm = get_model("qwen2.5vl")
    llm = llm.with_structured_output(Answer)
    for problem_name, problem in PROBLEMS.items():
        user_content = [{"type": "text","text": f"Problem: {problem["problem"]}\nAnswer: {problem["answer"]}"}]
        for img in problem["images"]:
            user_content.append(image_content(img))
        msgs = [
            {
                "role": "system",
                "content": f"I will give you a multiple-choice {DOMAIN} problem with images and its answer. The first image is the system diagram of the problem, and the second image contains the choices. First, describe the diagram of the problem. Then, provide a rationale for the given correct answer."
            },
            {
                "role": "user",
                "content": user_content
            }
            ]
        description = llm.invoke(msgs)
        with open(os.path.join("problems", problem_name, "description.json"), "w") as f:
            json.dump(description.model_dump(), f, indent=4)