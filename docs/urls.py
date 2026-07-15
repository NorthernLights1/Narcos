from django.urls import path

from docs import views, views_attachments

urlpatterns = [
    path("<int:pk>/attachments/upload/", views_attachments.attachment_upload,
         name="attachment_upload"),
    path("attachments/<int:pk>/download/", views_attachments.attachment_download,
         name="attachment_download"),
    path("attachments/<int:pk>/delete/", views_attachments.attachment_delete,
         name="attachment_delete"),
    path("attachments/<int:pk>/void/", views_attachments.attachment_void,
         name="attachment_void"),
    path("", views.document_list, name="document_list"),
    path("new/<str:doc_type>/", views.document_create, name="document_create"),
    path("<int:pk>/", views.document_detail, name="document_detail"),
    path("<int:pk>/print/", views.document_print, name="document_print"),
    path("<int:pk>/withholding-certificate/", views.withholding_certificate_print,
         name="withholding_certificate_print"),
    path("<int:pk>/edit/", views.document_edit, name="document_edit"),
    path("<int:pk>/convert-sale/", views.document_convert_sale, name="document_convert_sale"),
    path("<int:pk>/post/", views.document_post, name="document_post"),
    path("<int:pk>/void/", views.document_void, name="document_void"),
    path("<int:pk>/delete/", views.document_delete, name="document_delete"),
]
