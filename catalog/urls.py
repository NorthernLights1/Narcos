from django.urls import path

from catalog import views

urlpatterns = [
    path("<slug:kind>/", views.master_list, name="master_list"),
    path("<slug:kind>/new/", views.master_form, name="master_create"),
    path("<slug:kind>/<int:pk>/edit/", views.master_form, name="master_edit"),
    path("<slug:kind>/search/", views.master_search, name="master_search"),
    path("<slug:kind>/import/", views.csv_import, name="csv_import"),
]
