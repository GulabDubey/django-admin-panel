import json

import razorpay
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from packages.models import Package
from .models import Payment


def get_client():
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


@require_POST
def create_order(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request body."}, status=400)

    package = get_object_or_404(Package, id=data.get("package_id"), status="active")

    if package.is_custom_price or not package.price:
        return JsonResponse({"error": "This plan requires contacting sales."}, status=400)

    buyer_name = (data.get("name") or "").strip()
    buyer_email = (data.get("email") or "").strip()
    buyer_contact = (data.get("contact") or "").strip()

    if not buyer_name or not buyer_email:
        return JsonResponse({"error": "Name and email are required."}, status=400)

    amount_paise = int(package.price * 100)

    try:
        order = get_client().order.create({
            "amount": amount_paise,
            "currency": "INR",
            "payment_capture": 1,
            "notes": {"package": package.name, "email": buyer_email},
        })
    except razorpay.errors.BadRequestError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

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
        "razorpay_payment_id": data.get("razorpay_payment_id"),
        "razorpay_signature": data.get("razorpay_signature"),
    }

    try:
        get_client().utility.verify_payment_signature(params_dict)
    except razorpay.errors.SignatureVerificationError:
        payment.status = "failed"
        payment.save(update_fields=["status", "updated_at"])
        return JsonResponse({"status": "failed"}, status=400)

    payment.razorpay_payment_id = params_dict["razorpay_payment_id"]
    payment.razorpay_signature = params_dict["razorpay_signature"]
    payment.status = "paid"
    payment.save()

    return JsonResponse({"status": "success"})
