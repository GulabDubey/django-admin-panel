from crewai import LLM
from django.conf import settings


def get_llm():

    return LLM(
        model=settings.ANTHROPIC_MODEL,
        api_key=settings.ANTHROPIC_API_KEY,
        temperature=0.7
    )
