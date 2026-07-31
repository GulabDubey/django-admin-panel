from django import forms
from .models import Blog


class BlogAdminForm(forms.ModelForm):

    class Meta:
        model = Blog
        fields = "__all__"