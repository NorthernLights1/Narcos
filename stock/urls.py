from django.urls import path

from stock import views

urlpatterns = [
    path("", views.inventory_list, name="inventory_list"),
    path("<int:pk>/", views.inventory_item, name="inventory_item"),
]
