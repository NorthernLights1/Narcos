from django.urls import path

from reports import views

urlpatterns = [
    path("", views.report_hub, name="report_hub"),
    path("finance/", views.finance, name="finance"),
    path("statement/", views.statement, name="statement"),
    # D135/D141: must precede the catch-all, or the slug pattern swallows them.
    path("positions/<slug:side>/", views.party_positions, name="party_positions"),
    path("sales/", views.sales_report, name="sales_report"),
    path("<slug:slug>/", views.report_detail, name="report_detail"),
]
