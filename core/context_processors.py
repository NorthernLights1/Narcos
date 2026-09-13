"""Template context shared by every page.

D150: the version stamp. Support here happens over a phone photo of the screen
with no remote access to the machine, so every page has to say which build drew
it. The value comes from the environment (the release workflow stamps the image
with the tag it built), never from a constant in the source — a literal would
have to be remembered at release time, and a stamp nobody remembers to bump is
worse than none.
"""

from django.conf import settings


def version_stamp(request) -> dict:
    """Expose the running build's version to every template."""
    return {"narcos_version": settings.NARCOS_VERSION}
