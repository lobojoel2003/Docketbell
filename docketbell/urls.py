from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from docketbell import health

urlpatterns = [
    path("", include("docketbell.dashboard.urls")),
    path("sms/", include("docketbell.sms.urls")),
    path("healthz", health.healthz, name="healthz"),
    path("version.json", health.version, name="version"),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(redirect_authenticated_user=True),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("i18n/", include("django.conf.urls.i18n")),
    path("admin/", admin.site.urls),
]
