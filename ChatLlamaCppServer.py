from typing import (
    List,
    Optional,
    Any,
)
import requests
from pydantic import Field
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    convert_to_openai_messages
)
from langchain_core.language_models.chat_models import BaseChatModel

class ChatLlamaCppServer(BaseChatModel):
    """
    A chat model that uses the LlamaCpp server for local inference.
    This model is designed to work with the LlamaCpp server, which should be running
    locally at the specified server URL.
    This should be used for utility-based multimodal retrieval until Ollama supports logprobs or 
    llama-cpp-python correctly supports Metal on Mac (I had trouble installing it on my Mac).
    """

    model_name: str = Field(alias="model")
    """The name of the model"""
    server_url: str = Field(default="http://127.0.0.1:8080/v1/chat/completions")
    """The number of characters from the last message of the prompt to be echoed."""
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    timeout: Optional[int] = None
    stop: Optional[List[str]] = None
    max_retries: int = 2
    logprobs: Optional[bool] = False
    top_logprobs: Optional[int] = None
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        payload = {
            "model":      self.model_name,
            "messages":   convert_to_openai_messages(messages),
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "logprobs":  kwargs.get('logprobs', self.logprobs),
            "top_logprobs": kwargs.get("top_logprobs", self.top_logprobs)
        }
        resp = requests.post(self.server_url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        
        data["usage"]["input_tokens"] = data["usage"]["prompt_tokens"]
        data["usage"]["output_tokens"] = data["usage"]["completion_tokens"]
        message = AIMessage(
            content=data["choices"][0]["message"]["content"],
            additional_kwargs={},  # Used to add additional payload to the message
            response_metadata=data["choices"][0],
            usage_metadata=data["usage"],
        )
        generation = ChatGeneration(message=message)
        print(generation)
        return ChatResult(generations=[generation])
    
    @property
    def _llm_type(self) -> str:
        """Get the type of language model used by this chat model."""
        return self.model_name + "-llamacpp-local"