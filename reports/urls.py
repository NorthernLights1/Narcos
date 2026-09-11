from django.urls import path

from reports import views

urlpatterns = [
    path("", views.report_hub, name="report_hub"),
    path("finance/", views.finance, name="finance"),
    path("statement/", views.statement, name="statement"),
    # D135: must precede the catch-all, or the slug pattern swallows it.
    path("positions/<slug:side>/", views.party_positions, name="party_positions"),
    path("<slug:slug>/", views.report_detail, name="report_detail"),
]
