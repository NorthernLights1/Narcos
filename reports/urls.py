from django.urls import path

from reports import views

urlpatterns = [
    path("", views.report_hub, name="report_hub"),
    path("<slug:slug>/", views.report_detail, name="report_detail"),
]
