from crewai import Crew


from .agents import (
    get_research_agent,
    get_writer_agent,
    get_reviewer_agent
)


from .tasks import create_tasks



def generate_blog(topic):


    research_agent = (
        get_research_agent()
    )

    writer_agent = (
        get_writer_agent()
    )

    reviewer_agent = (
        get_reviewer_agent()
    )


    tasks = create_tasks(

        topic,

        research_agent,

        writer_agent,

        reviewer_agent

    )



    crew = Crew(

        agents=[

            research_agent,

            writer_agent,

            reviewer_agent

        ],

        tasks=tasks,


        process="sequential",

        verbose=True

    )



    result = crew.kickoff()


    return result