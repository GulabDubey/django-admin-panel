import os
from crewai import LLM

def get_llm():

    return LLM(
        model="anthropic/claude-sonnet-4-5",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        temperature=0.7
    )