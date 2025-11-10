from langchain_openai import ChatOpenAI
from config.prompt import ELABORATE_PROMPT
from dotenv import load_dotenv
load_dotenv()
class LLMService:
    def __init__(self, model: str = "gpt-4o-mini"):
        self.llm=ChatOpenAI(model=model)
    def elaborate_prompt(self, prompt: str) -> str:
        return self.llm.invoke(ELABORATE_PROMPT.format(prompt=prompt)).content