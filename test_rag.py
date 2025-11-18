import os
import json
import pickle
from byaldi import RAGMultiModalModel
from utils import get_device
from domain_information import TEXT_PATH, PROBLEMS, INDEX_NAME

if __name__ == "__main__":
    model_name = "qwen2.5vl"
    index_root = "./index"
    index_name = INDEX_NAME
    text_path = TEXT_PATH
    index_model = "vidore/colqwen2.5-v0.2"

    if not os.path.exists(os.path.join(index_root, index_name)):
        rag = RAGMultiModalModel.from_pretrained(
        index_model,
        index_root=index_root,
        device=get_device()
        )

        rag.index(
            input_path=text_path,
            index_name=index_name,
            overwrite=False
            )
    else:
        rag = RAGMultiModalModel.from_index(
            index_path=index_name,
            index_root=index_root,
            device=get_device()
        )
    
    for problem_name, problem in PROBLEMS.items():
        with open(os.path.join("problems", problem_name, "description.json"), "r") as f:
            description = json.load(f)
        results = rag.search(description["rationale"], k=5)
        pages = []
        for result in results:
            pages.append(result["page_num"])
        print(problem_name, pages)
        with open(os.path.join("problems", problem_name, "pages_rationale.pkl"), "wb") as f:
            pickle.dump(pages, f)
