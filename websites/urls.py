from django.urls import path
from .views import consume_question_view, llm_config, refund_question_view, verify_subscription

urlpatterns = [
    path("verify-subscription/", verify_subscription, name="chatbot_verify_subscription"),
    path("llm-config/", llm_config, name="chatbot_llm_config"),
    path("questions/consume/", consume_question_view, name="chatbot_consume_question"),
    path("questions/refund/", refund_question_view, name="chatbot_refund_question"),
]
