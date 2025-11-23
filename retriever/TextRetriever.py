from typing import List, Iterable
from numpy import argsort
from scipy.special import softmax
from llm_utils import get_model, image_content

SERVER_URL  = "http://127.0.0.1:8080/v1/chat/completions"

class TextRetriever:
    def __init__(self,
                 model_name: str,
                 text_path: str,
                 base_messages: List[dict] = None,
                 top_logprobs: int = 15,
                 **kwargs):
        self.model = get_model(
            model_name,
            max_tokens=1,
            temperature=0,
            server_url=SERVER_URL
            ).bind(logprobs=True, top_logprobs=top_logprobs)
        self.text_path = text_path
        if base_messages is None:
            self.base_messages = []
        else:
            self.base_messages = base_messages

    def image_content(self, image_path: str) -> List[dict]:
        return image_content(image_path)

    def get_user_content(self, problem: dict, document) -> List[dict]:
        raise NotImplementedError("This method should be implemented in subclasses.")
    
    def get_choice_logprob(self, problem: dict, document) -> List[dict]:
        # clone the base messages and append the forced‐completion prompt
        user_content = self.get_user_content(problem, document)
        msgs = self.base_messages + [{
            "role": "user",
            "content": user_content
        }]

        response = self.model.invoke(msgs)
        return response.response_metadata["logprobs"]["content"][0]["top_logprobs"]

    def get_prob(self, result: List[dict],
                choices: List[str] = ["a", "b", "c", "d", "e"]):
        logprobs = {}
        for item in result:
            if item["token".lower()] in choices and item["token".lower()] not in logprobs:
                logprobs[item["token"].lower()] = item["logprob"]
        prob_list = []
        for c in choices:
            if c not in logprobs:
                logprobs[c] = float("-inf")
            prob_list.append(logprobs[c])
        return softmax(prob_list)
    
    def retrieve_loop(self, problem: dict, documents: Iterable):
        scores = []
        correct_idx = problem["choices"].index(problem["answer"])
        for doc in documents:
            res = self.get_choice_logprob(problem, doc)
            prob = self.get_prob(res, problem["choices"])
            scores.append(prob[correct_idx])
            print("Correct Probability:", prob[correct_idx])
        ranked = argsort(scores)[::-1]
        return ranked
    
    def retrieve(self, problem: dict, k=5) -> list:
        raise NotImplementedError("This method should be implemented in subclasses.")