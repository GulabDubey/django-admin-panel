from crewai import Agent

from .llm import get_llm



def get_research_agent():

    return Agent(

        role="Blog Research Specialist",

        goal="""
        Research topics deeply.
        Find accurate information,
        trends, examples and facts.
        """,

        backstory="""
        You are an expert researcher
        who prepares detailed notes
        for professional writers.
        """,

        llm=get_llm(),

        verbose=True

    )



def get_writer_agent():

    return Agent(

        role="SEO Blog Writer",

        goal="""
        Create high quality SEO
        optimized blog articles.
        """,

        backstory="""
        You are an experienced
        technical content writer.
        """,

        llm=get_llm(),

        verbose=True

    )



def get_reviewer_agent():

    return Agent(

        role="Senior Content Editor",

        goal="""
        Improve blog quality,
        SEO, readability and accuracy.
        """,

        backstory="""
        You are a senior editor
        working for a technology
        publication.
        """,

        llm=get_llm(),

        verbose=True

    )