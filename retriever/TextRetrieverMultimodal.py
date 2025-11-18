import tempfile
import os
from typing import List
from pdf2image import convert_from_path
from domain_information import PROBLEMS, TEXT_PATH, DOMAIN
from TextRetriever import TextRetriever

# prepare messages: one system message + one image message per file + the text prompt
base_messages = [
    {"role": "system", "content": f"I will give you a multiple-choice {DOMAIN} problem. The first image is the system diagram of the problem, the second image contains the choices, and the third image is a page in a textbook that may help you answer. Output only the letter (a-e) of the correct answer without any justifications."},
]

class TextRetrieverMultimodal(TextRetriever):

    def get_user_content(self, problem: dict, document) -> List[dict]:
        user_content = []
        for img_path in problem["images"]:
            user_content.append(self.image_content(img_path))
        user_content.append(self.image_content(document))
        user_content.append({"type": "text", "text": problem["problem"]})
        return user_content
    
    def retrieve(self, problem: dict, k=5) -> List[int]:
        with tempfile.TemporaryDirectory() as path:
            text_images = convert_from_path(
                self.text_path,
                thread_count=os.cpu_count() - 1,
                output_folder=path,
                paths_only=True,
                dpi=300,
                fmt="png"
            )
            ranked = self.retrieve_loop(problem, text_images)
        return ranked[:k] + 1

if __name__ == "__main__":
    model_name  = ["qwen2.5-vl", "gpt-4.1-nano"][1]
    retriever = TextRetrieverMultimodal(model_name, TEXT_PATH, base_messages)
    for problem in PROBLEMS:
        res = retriever.retrieve(problem, 5)
        print("Top 5 ranked pages:", res)
