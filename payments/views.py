import json
import logging

import razorpay
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.ratelimit import ratelimit
from packages.models import Package
from .models import Payment

logger = logging.getLogger(__name__)


def get_client():
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def mark_paid(payment, razorpay_payment_id, razorpay_signature=""):
    """Mark a payment as paid. Safe to call more than once for the same order."""
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.status == "paid":
            return payment
        payment.razorpay_payment_id = razorpay_payment_id
        if razorpay_signature:
            payment.razorpay_signature = razorpay_signature
        payment.status = "paid"
        payment.save()
    logger.info("Payment %s marked paid (order %s)", payment.pk, payment.razorpay_order_id)
    return payment


@require_POST
@ratelimit("create_order", limit=20, period=600)
def create_order(request):
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        logger.error("Razorpay keys are not configured.")
        return JsonResponse({"error": "Payments are temporarily unavailable."}, status=503)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request body."}, status=400)

    package = get_object_or_404(Package, id=data.get("package_id"), status="active")

    if package.is_custom_price or not package.price:
        return JsonResponse({"error": "This plan requires contacting sales."}, status=400)

    buyer_name = (data.get("name") or "").strip()[:255]
    buyer_email = (data.get("email") or "").strip().lower()
    buyer_contact = (data.get("contact") or "").strip()[:20]

    if not buyer_name or not buyer_email:
        return JsonResponse({"error": "Name and email are required."}, status=400)

    try:
        validate_email(buyer_email)
    except ValidationError:
        return JsonResponse({"error": "Enter a valid email address."}, status=400)

    amount_paise = int(package.price * 100)

    try:
        order = get_client().order.create({
            "amount": amount_paise,
            "currency": "INR",
            "payment_capture": 1,
            "notes": {"package": package.name, "email": buyer_email},
        })
    except razorpay.errors.BadRequestError as exc:
        logger.warning("Razorpay rejected order for package %s: %s", package.pk, exc)
        return JsonResponse({"error": "Could not create the order. Please try again."}, status=400)
    except Exception:
        logger.exception("Razorpay order creation failed for package %s", package.pk)
        return JsonResponse({"error": "Payment gateway is unavailable. Please try again."}, status=502)

    payment = Payment.objects.create(
        user=request.user if request.user.is_authenticated else None,
        package=package,
        buyer_name=buyer_name,
        buyer_email=buyer_email,
        buyer_contact=buyer_contact,
        razorpay_order_id=order["id"],
        amount=package.price,
        status="created",
    )

    return JsonResponse({
        "order_id": order["id"],
        "amount": amount_paise,
        "currency": "INR",
        "key": settings.RAZORPAY_KEY_ID,
        "package_name": package.name,
        "payment_id": payment.id,
    })


@require_POST
def verify_payment(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request body."}, status=400)

    razorpay_order_id = data.get("razorpay_order_id")
    payment = get_object_or_404(Payment, razorpay_order_id=razorpay_order_id)

    params_dict = {
        "razorpay_order_id": razorpay_order_id,
        "razorpay_payment_id": data.get("razorpay_payment_id") or "",
        "razorpay_signature": data.get("razorpay_signature") or "",
    }

    try:
        get_client().utility.verify_payment_signature(params_dict)
    except razorpay.errors.SignatureVerificationError:
        logger.warning("Invalid payment signature for order %s", razorpay_order_id)
        # Never downgrade a payment the webhook already confirmed.
        Payment.objects.filter(pk=payment.pk).exclude(status="paid").update(
            status="failed", updated_at=timezone.now()
        )
        return JsonResponse({"status": "failed"}, status=400)

    mark_paid(payment, params_dict["razorpay_payment_id"], params_dict["razorpay_signature"])

    return JsonResponse({"status": "success"})


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """
    Server-to-server confirmation from Razorpay. Covers payments where the
    buyer closed the browser before /verify/ was called.

    Configure in Razorpay Dashboard → Webhooks with events
    `payment.captured` and `payment.failed`, pointing at
    https://<your-domain>/api/payments/webhook/
    """
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not secret:
        logger.error("Razorpay webhook received but RAZORPAY_WEBHOOK_SECRET is not set.")
        return HttpResponse(status=503)

    signature = request.headers.get("X-Razorpay-Signature", "")
    body = request.body.decode("utf-8")

    try:
        get_client().utility.verify_webhook_signature(body, signature, secret)
    except razorpay.errors.SignatureVerificationError:
        logger.warning("Rejected Razorpay webhook with invalid signature.")
        return HttpResponse(status=400)

    try:
        event = json.loads(body)
        entity = event["payload"]["payment"]["entity"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return HttpResponse(status=400)

    payment = Payment.objects.filter(razorpay_order_id=entity.get("order_id")).first()
    if payment is None:
        # Not an order created by this app; acknowledge so Razorpay stops retrying.
        return HttpResponse(status=200)

    event_type = event.get("event")
    if event_type == "payment.captured":
        if entity.get("amount") != int(payment.amount * 100):
            logger.error(
                "Amount mismatch for order %s: expected %s, got %s",
                payment.razorpay_order_id, int(payment.amount * 100), entity.get("amount"),
            )
            return HttpResponse(status=200)
        mark_paid(payment, entity.get("id", ""))
    elif event_type == "payment.failed":
        Payment.objects.filter(pk=payment.pk, status="created").update(
            status="failed", updated_at=timezone.now()
        )

    return HttpResponse(status=200)
