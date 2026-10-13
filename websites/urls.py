from django.urls import path
from .views import verify_subscription

urlpatterns = [
    path("verify-subscription/", verify_subscription, name="chatbot_verify_subscription"),
]
