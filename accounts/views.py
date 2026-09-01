import json

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from .models import Profile


@require_POST
def register_view(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request body."}, status=400)

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    contact = (data.get("contact") or "").strip()
    password = data.get("password") or ""
    confirm_password = data.get("confirm_password") or ""

    if not name or not email or not contact or not password:
        return JsonResponse({"error": "All fields are required."}, status=400)

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"error": "Enter a valid email address.", "field": "email"}, status=400)

    if password != confirm_password:
        return JsonResponse({"error": "Passwords do not match.", "field": "confirm_password"}, status=400)

    if len(password) < 8:
        return JsonResponse({"error": "Password must be at least 8 characters.", "field": "password"}, status=400)

    if User.objects.filter(email__iexact=email).exists():
        return JsonResponse({"error": "An account with this email already exists.", "field": "email"}, status=400)

    user = User.objects.create_user(username=email, email=email, password=password, first_name=name[:150])
    Profile.objects.create(user=user, contact=contact)

    login(request, user)

    return JsonResponse({"name": user.first_name, "email": user.email})


@require_POST
def login_view(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request body."}, status=400)

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    remember = bool(data.get("remember"))

    if not email or not password:
        return JsonResponse({"error": "Email and password are required."}, status=400)

    user = authenticate(request, username=email, password=password)
    if user is None:
        return JsonResponse({"error": "Invalid email or password."}, status=400)

    login(request, user)
    request.session.set_expiry(1209600 if remember else 0)

    return JsonResponse({"name": user.first_name or user.email, "email": user.email})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("home")
