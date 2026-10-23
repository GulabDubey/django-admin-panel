from django.core.management.base import BaseCommand
from django.db import transaction

from llm import crypto
from llm.models import LLMProvider


class Command(BaseCommand):
    help = "Re-encrypt every stored LLM API key with the first key in LLM_ENCRYPTION_KEYS."

    def handle(self, *args, **options):
        with transaction.atomic():
            providers = LLMProvider.objects.select_for_update().exclude(api_key_encrypted="")
            for provider in providers:
                provider.api_key_encrypted = crypto.rotate(provider.api_key_encrypted)
                provider.save(update_fields=["api_key_encrypted", "updated_at"])
                self.stdout.write(f"Re-encrypted key for {provider.name}")
        self.stdout.write(self.style.SUCCESS("Done. Old keys can now be removed from LLM_ENCRYPTION_KEYS."))
