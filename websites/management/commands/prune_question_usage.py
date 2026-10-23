from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from websites.models import QuestionUsage
from websites.questions import TOTAL_PERIOD_START


class Command(BaseCommand):
    help = "Delete chatbot question counters of periods that ended long ago (keeps 'in total' counters)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=45, help="Keep counters newer than this many days.")

    def handle(self, *args, days, **options):
        cutoff = timezone.now() - timedelta(days=days)
        deleted, _ = QuestionUsage.objects.filter(period_start__lt=cutoff).exclude(
            period_start=TOTAL_PERIOD_START
        ).delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} old question counters."))
