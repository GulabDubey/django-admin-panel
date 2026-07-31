from django.http import JsonResponse
from .models import Package


def package_list(request):

    data = []

    for package in Package.objects.all():

        data.append({
            "id": package.id,
            "title": package.title,
            "description": package.description,
            "price": str(package.price),
            "image": package.image.url if package.image else ""
        })

    return JsonResponse(data, safe=False)