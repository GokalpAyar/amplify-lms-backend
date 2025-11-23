import re
import base64
from typing import Optional, List
from dotenv import load_dotenv
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel
from ChatLlamaCppServer import ChatLlamaCppServer

load_dotenv()

def get_model(
        model_name: str,
        temperature: Optional[float] = 0.0,
        max_tokens: Optional[int] = 2048,
        max_retries: Optional[int] = 3,
        server_url: Optional[str] = "http://127.0.0.1:8080/v1/chat/completions"
        ) -> BaseChatModel:
    if model_name == "deepseek-chat":
        llm = ChatDeepSeek(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=max_retries,
        )
    elif model_name == "deepseek-r1" or model_name == "qwen2.5vl":
        llm = ChatOllama(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=max_retries,
        )
    elif "gpt" in model_name or re.search(r"o\d", model_name):
        if re.search(r"o\d", model_name):
            temperature = 1
        llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=max_retries,
        )
    elif "vl" in model_name:
        llm = ChatLlamaCppServer(
            model=model_name,
            server_url=server_url
        )
    else:
        raise NotImplementedError(f"Model {model_name} is not supported.")
    return llm

def image_content(image_path: str) -> List[dict]:
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}

if __name__ == "__main__":
    llm = get_model("qwen2.5-vl").bind(logprobs=True, top_logprobs=15)
    print(llm.invoke(
        [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is the capital of Japan?"}
        ]
    ))