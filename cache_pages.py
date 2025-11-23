import pickle
import os
from domain_information import PROBLEMS, TEXT_PATH, INDEX_NAME
from retriever.TextRetrieverConcepts import TextRetrieverConcepts

model_name = "qwen2.5vl"
index_root = "./index"
retriever = TextRetrieverConcepts(model_name, TEXT_PATH, index_root, INDEX_NAME)

for problem_name ,problem in PROBLEMS.items():
    pkl_path = os.path.join("problems", problem_name, "pages.pkl")
    if not os.path.exists(pkl_path):
        pages = retriever.retrieve(problem)
        print(problem_name, pages)
        with open(pkl_path, "wb") as f:
            pickle.dump(pages, f)
