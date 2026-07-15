from django.urls import path

from reports import views

urlpatterns = [
    path("", views.report_hub, name="report_hub"),
    path("finance/", views.finance, name="finance"),
    path("statement/", views.statement, name="statement"),
    path("<slug:slug>/", views.report_detail, name="report_detail"),
]
