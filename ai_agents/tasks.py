from crewai import Task

def create_tasks(
        topic,
        research_agent,
        writer_agent,
        reviewer_agent
):

    research_task = Task(
        description=f"""
        Research this blog topic:
        {topic}
        Provide:
        - Important facts
        - Latest trends
        - User problems
        - Content outline
        - Keywords
        """,
        agent=research_agent,
        expected_output="""
        Research document
        containing facts,
        outline and keywords.
        """
    )

    writing_task = Task(
        description="""
        Write a complete SEO blog
        using the research notes.
        Format:
        TITLE:
        META DESCRIPTION:
        CONTENT:
        Requirements:
        - SEO friendly
        - Clear headings
        - Examples
        - Conclusion
        """,

        agent=writer_agent,


        context=[
            research_task
        ],


        expected_output="""

        Complete blog article
        with title, meta description
        and content.

        """

    )



    review_task = Task(

        description="""

        Review the written blog.


        Improve:

        - Grammar
        - SEO
        - Structure
        - Accuracy


        Return only final article.

        """,


        agent=reviewer_agent,


        context=[
            writing_task
        ],


        expected_output="""

        Final production-ready
        blog content.

        """

    )


    return [
        research_task,
        writing_task,
        review_task
    ]