from django.conf import settings


def site_settings(request):
    return {
        "CHATBOT_WIDGET_URL": settings.CHATBOT_WIDGET_URL,
    }
