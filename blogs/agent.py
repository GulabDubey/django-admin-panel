import os
from crewai import Agent, Task, Crew

from langchain_anthropic import ChatAnthropic

def get_llm():
    return ChatAnthropic(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4"),
        temperature=0.7
    )

llm = get_llm()

research_agent = Agent(
    role="Blog Research Specialist",

    goal="""
    Find useful information,
    statistics and trends
    about given topic.
    """,

    backstory="""
    Expert researcher who
    collects accurate information
    for technical blogs.
    """,

    llm=llm,

    verbose=True
)

writer_agent = Agent(

    role="Professional Blog Writer",

    goal="""
    Write engaging SEO optimized
    blog articles.
    """,

    backstory="""
    Experienced content writer
    who writes developer friendly
    blogs.
    """,

    llm=llm,

    verbose=True
)

reviewer_agent = Agent(

    role="Content Reviewer",

    goal="""
    Review blog quality,
    grammar and SEO.
    Improve the article.
    """,

    backstory="""
    Senior editor with years
    of publishing experience.
    """,

    llm=llm,

    verbose=True
)

def create_blog_tasks(topic):

    research_task = Task(

        description=f"""
        Research the topic:

        {topic}

        Provide:
        - key points
        - facts
        - outline
        """,

        agent=research_agent,

        expected_output="""
        Detailed research notes
        """
    )

    writing_task = Task(

        description="""

        Using research,
        write a complete blog.

        Include:

        - title
        - introduction
        - headings
        - conclusion
        - SEO description

        """,

        agent=writer_agent,

        expected_output="""
        Complete blog article
        """
    )

    review_task = Task(

        description="""

        Review the blog.

        Fix:
        - grammar
        - structure
        - SEO issues

        Return final version.

        """,

        agent=reviewer_agent,

        expected_output="""
        Final polished blog
        """
    )


    return [
        research_task,
        writing_task,
        review_task
    ]

def generate_blog(topic):
    tasks = create_blog_tasks(topic)
    crew = Crew(
        agents=[
            research_agent,
            writer_agent,
            reviewer_agent
        ],
        tasks=tasks,
        verbose=True
    )
    result = crew.kickoff()
    return result