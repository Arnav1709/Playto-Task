from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("payouts.urls")),
    path("", TemplateView.as_view(template_name="index.html"), name="frontend-root"),
    re_path(r"^(?!api/|admin/|static/).*", TemplateView.as_view(template_name="index.html")),
]

