import os
import tempfile
from typing import List
from byaldi import RAGMultiModalModel
from pydantic import BaseModel, Field
import inflect
from pdf2image import convert_from_path
import torch
from utils import get_device
from domain_information import PROBLEMS, TEXT_PATH, DOMAIN, INDEX_NAME
from TextRetriever import TextRetriever

class Concepts(BaseModel):
    concepts: List[str] = Field(description="List of concepts required to solve the problem.")

class TextRetrieverConcepts(TextRetriever):
    def __init__(self,
                 model_name: str,
                 text_path: str,
                 index_root: str,
                 index_name: str,
                 base_messages: List[dict] = None,
                 top_logprobs: int = 15,
                 **kwargs):
        super().__init__(model_name, text_path, base_messages, top_logprobs, **kwargs)
        self.model = self.model.with_structured_output(Concepts)
        index_model = kwargs.get("index_model", "vidore/colqwen2.5-v0.2")
        if not os.path.exists(os.path.join(index_root, index_name)):
            self.rag = RAGMultiModalModel.from_pretrained(
            index_model,
            index_root=index_root,
            device=get_device()
            )

            self.rag.index(
                input_path=text_path,
                index_name=index_name,
                overwrite=False
                )
        else:
            self.rag = RAGMultiModalModel.from_index(
                index_path=index_name,
                index_root=index_root,
                device=get_device()
            )
        self.p = inflect.engine()

    def get_user_content(self, problem: dict, document):
        user_content = [{
            "type": "text",
            "text": f"List the {DOMAIN} concepts that are required to solve the following problem.\nProblem: {problem["problem"]}"}]
        user_content.append(self.image_content(problem["images"][0]))
        return user_content
    
    def retrieve(self, problem: dict, k=5) -> List[int]:
        user_content = self.get_user_content(problem, None)
        msgs = self.base_messages + [{
            "role": "user",
            "content": user_content
        }]

        concepts = self.model.invoke(msgs).concepts
        pages = set()
        for concept in concepts:
            if self.p.singular_noun(concept):
                query = f"What is {concept}?"
            else:
                query = f"What are {concept}?"
            results = self.rag.search(query, 3)
            for result in results:
                pages.add(result["page_num"])
        pages = sorted(pages)
        
        req_embeddings = []
        for page in pages:
            with tempfile.TemporaryDirectory() as path:
                text_images = convert_from_path(
                    self.text_path,
                    thread_count=os.cpu_count() - 1,
                    output_folder=path,
                    dpi=300,
                    fmt="png",
                    first_page=page,
                    last_page=page
                )
            with torch.inference_mode():
                batch_query = self.rag.model.processor.process_images(text_images)
                batch_query = {k: v.to(self.rag.model.device).to(self.rag.model.model.dtype if v.dtype in [torch.float16, torch.bfloat16, torch.float32] else v.dtype) for k, v in batch_query.items()}
                embeddings_query = self.rag.model.model(**batch_query)
                req_embeddings.append(torch.unbind(embeddings_query.to("cpu"))[0])
        
        with torch.inference_mode():
            batch_query = self.rag.model.processor.process_queries([problem["problem"]])
            batch_query = {k: v.to(self.rag.model.device).to(self.rag.model.model.dtype if v.dtype in [torch.float16, torch.bfloat16, torch.float32] else v.dtype) for k, v in batch_query.items()}
            embeddings_query = self.rag.model.model(**batch_query)
            qs = list(torch.unbind(embeddings_query.to("cpu")))
            scores = self.rag.model.processor.score(qs,req_embeddings).cpu().numpy()
        top_pages = scores.argsort(axis=1)[0][-k:][::-1].tolist()

        return [pages[i] for i in top_pages]

os.environ["TOKENIZERS_PARALLELISM"] = "false"

if __name__ == "__main__":
    model_name = "qwen2.5vl"
    index_root = "./index"

    rag = TextRetrieverConcepts(
        model_name,
        TEXT_PATH,
        index_root,
        INDEX_NAME
    )

    print(rag.retrieve(PROBLEMS[0], 5))
