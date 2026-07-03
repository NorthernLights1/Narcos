from django.apps import AppConfig


class DocsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "docs"

    def ready(self):
        # Handler registration is an import side effect — fail fast at startup
        # rather than "No handler for document type" at request time.
        from docs import handlers, handlers_sales, posting  # noqa: F401
