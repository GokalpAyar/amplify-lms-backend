import os
import ast
from typing import List

from langchain_docling.loader import ExportType
from langchain_docling import DoclingLoader
from docling.chunking import HybridChunker
import pandas as pd

from domain_information import PROBLEMS, TEXT_PATH, DOMAIN
from TextRetriever import TextRetriever

class TextRetrieverChunk(TextRetriever):

    def get_user_content(self, problem: dict, document) -> List[dict]:
        user_content = []
        for img_path in problem["images"]:
            user_content.append(self.image_content(img_path))
        user_content.append({
            "type": "text",
            "text": problem["problem"] 
            + f"Relevant knowledge from a textbook is below.\n---------------------\n{document}\n---------------------"
        })
        return user_content
    
    def index(self):
        if os.path.exists(f"{self.text_path}.xlsx"):
            df = pd.read_excel(f"{self.text_path}.xlsx")
            df["pages"] = df["pages"].apply(ast.literal_eval)
        else:
            export_type = ExportType.DOC_CHUNKS
            embed_model_id = "sentence-transformers/all-mpnet-base-v2"
            loader = DoclingLoader(
                file_path=[self.text_path],
                export_type=export_type,
                chunker=HybridChunker(tokenizer=embed_model_id, max_tokens=1024),
            )
            docs = loader.load()
            chunks = []
            for doc in docs:
                doc_items = doc.metadata["dl_meta"]["doc_items"]
                pages = set()
                for item in doc_items:
                    for prov in item["prov"]:
                        pages.add(prov["page_no"])
                chunks.append({
                    "text": doc.page_content,
                    "pages": pages
                })
            df = pd.DataFrame(chunks)
            df.to_excel(f"{TEXT_PATH}.xlsx", index=False)
        return df
    
    def retrieve(self, problem: dict, k=5) -> List[str]:
        df = self.index()
        chunks = df["text"].tolist()
        pages = df["pages"].tolist()
        ranked = self.retrieve_loop(problem, chunks)
        retrieved = []
        for i in ranked[:k]:
            retrieved.append(f"Pages: {pages[i]}, Text: {chunks[i]}")
        return retrieved

# https://github.com/huggingface/transformers/issues/5486:
os.environ["TOKENIZERS_PARALLELISM"] = "false"

base_messages = [
    {"role": "system", "content": f"I will give you a multiple-choice {DOMAIN} problem. The first image is the system diagram of the problem, and the second image contains the choices. I will also give some knowledge from a textbook that may help you answer. Output only the letter (a-e) of the correct answer without any justifications."},
]

if __name__ == "__main__":
    model_name  = ["qwen2.5-vl", "gpt-4.1-nano"][0]
    retriever = TextRetrieverChunk(model_name, TEXT_PATH, base_messages)
    for problem in PROBLEMS:
        res = retriever.retrieve(problem, 5)
        print("Top 5 ranked pages:", res)
