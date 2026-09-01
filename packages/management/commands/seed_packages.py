from django.core.management.base import BaseCommand
from packages.models import Package

DEFAULT_PACKAGES = [
    {
        "name": "Starter",
        "badge": "Starter",
        "price": 2999,
        "is_custom_price": False,
        "duration": 30,
        "description": "For a single website getting started with AI chat.",
        "features": "1 website\n500 AI chats\nBasic lead capture\nEmail support",
        "cta_text": "Start Free Trial",
        "cta_link": "#contact",
        "is_recommended": False,
        "order": 1,
    },
    {
        "name": "Professional",
        "badge": "Recommended",
        "price": 7999,
        "is_custom_price": False,
        "duration": 30,
        "description": "For growing teams that need analytics and handoff.",
        "features": "3 websites\n5,000 AI chats\nAnalytics dashboard\nHuman handoff",
        "cta_text": "Start Free Trial",
        "cta_link": "#contact",
        "is_recommended": True,
        "order": 2,
    },
    {
        "name": "Business",
        "badge": "Business",
        "price": 14999,
        "is_custom_price": False,
        "duration": 30,
        "description": "For businesses with multiple websites and documents.",
        "features": "10 websites\n25,000 AI chats\nPDF uploads\nPriority support",
        "cta_text": "Book Demo",
        "cta_link": "#contact",
        "is_recommended": False,
        "order": 3,
    },
    {
        "name": "Enterprise",
        "badge": "Enterprise",
        "price": None,
        "is_custom_price": True,
        "duration": 30,
        "description": "For large organizations that need custom workflows and security.",
        "features": "Custom AI workflows\nAdvanced security\nAPI access\nDedicated success manager",
        "cta_text": "Contact Sales",
        "cta_link": "#contact",
        "is_recommended": False,
        "order": 4,
    },
]


class Command(BaseCommand):
    help = "Seed the default pricing packages (Starter, Professional, Business, Enterprise)."

    def handle(self, *args, **options):
        for data in DEFAULT_PACKAGES:
            package, created = Package.objects.update_or_create(
                name=data["name"],
                defaults={**data, "status": "active"},
            )
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{action} package: {package.name}"))

        self.stdout.write(self.style.SUCCESS("Default packages seeded successfully."))
