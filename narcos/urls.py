from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("documents/", include("docs.urls")),
    path("inventory/", include("stock.urls")),
    path("reports/", include("reports.urls")),
    path("master/", include("catalog.urls")),
    path("", include("core.urls")),
]
