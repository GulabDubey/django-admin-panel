from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import Profile


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = "Profile"


class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline,)
    list_display = BaseUserAdmin.list_display + ("get_contact",)

    @admin.display(description="Contact")
    def get_contact(self, obj):
        profile = Profile.objects.filter(user=obj).first()
        return profile.contact if profile else ""


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
