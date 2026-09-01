from django.http import JsonResponse
from .models import Package


def package_list(request):

    data = []

    for package in Package.objects.filter(status="active"):

        data.append({
            "id": package.id,
            "name": package.name,
            "badge": package.badge,
            "description": package.description,
            "price": package.display_price(),
            "price_value": float(package.price) if package.price is not None else None,
            "is_custom_price": package.is_custom_price,
            "duration": package.duration,
            "features": package.feature_list(),
            "cta_text": package.cta_text,
            "cta_link": package.cta_link,
            "is_recommended": package.is_recommended,
        })

    return JsonResponse(data, safe=False)
