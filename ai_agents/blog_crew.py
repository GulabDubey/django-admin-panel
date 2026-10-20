import anthropic
from django.conf import settings


RESEARCH_SYSTEM = """
You are a Blog Research Specialist: an expert researcher
who prepares detailed notes for professional writers.
Research topics deeply. Find accurate information,
trends, examples and facts.
"""

WRITER_SYSTEM = """
You are an SEO Blog Writer: an experienced technical
content writer who creates high quality SEO optimized
blog articles.
"""

REVIEWER_SYSTEM = """
You are a Senior Content Editor working for a technology
publication. Improve blog quality, SEO, readability
and accuracy.
"""


def _model():
    # Settings may use the LiteLLM-style "anthropic/<model>" name.
    return settings.ANTHROPIC_MODEL.removeprefix("anthropic/")


def _ask(client, system, prompt):

    response = client.messages.create(
        model=_model(),
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )

    return "".join(
        block.text for block in response.content if block.type == "text"
    )


def generate_blog(topic):

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    research = _ask(client, RESEARCH_SYSTEM, f"""
Research this blog topic:
{topic}

Provide:
- Important facts
- Latest trends
- User problems
- Content outline
- Keywords

Return a research document containing facts, outline and keywords.
""")

    draft = _ask(client, WRITER_SYSTEM, f"""
Write a complete SEO blog on "{topic}" using these research notes:

<research>
{research}
</research>

Format:
TITLE:
META DESCRIPTION:
CONTENT:

Requirements:
- SEO friendly
- Clear headings
- Examples
- Conclusion
""")

    return _ask(client, REVIEWER_SYSTEM, f"""
Review this blog article:

<article>
{draft}
</article>

Improve:
- Grammar
- SEO
- Structure
- Accuracy

Return only the final, production-ready article.
""")
