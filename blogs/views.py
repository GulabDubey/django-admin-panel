from django.shortcuts import render, get_object_or_404
from .models import Blog


def blog_list(request):
    blogs = Blog.objects.filter(
        status="published"
    )

    return render(
        request,
        "blogs/list.html",
        {
            "blogs": blogs
        }
    )


def blog_detail(request, slug):

    blog = get_object_or_404(
        Blog,
        slug=slug,
        status="published"
    )

    return render(
        request,
        "blogs/detail.html",
        {
            "blog": blog
        }
    )