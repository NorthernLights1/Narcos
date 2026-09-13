"""D150: the version stamp, on every screen and in the startup log.

CLAUDE.md's support rule says every failure needs a photographable surface: a
message on screen, a line in the log, and a version stamp. The first two
existed; the third did not. Nothing in the app, `compose.yml`, `settings.py` or
any template carried a version, so a photograph of a broken screen could not
say which build produced it.

That gap had a real cost. The client ran v1.1.0 for four weeks and 47 commits
without anyone being able to tell from their machine which build they were on.

The rule these tests hold: **the version is visible on every screen and it
comes from the image, not from a string typed into the source.** A stamp that
has to be hand-edited at release time is a stamp that goes stale.
"""

import pytest
from django.test import override_settings
from django.urls import reverse

from core.context_processors import version_stamp

pytestmark = pytest.mark.django_db


def test_the_stamp_comes_from_the_environment_not_a_literal():
    """Release stamps the image; nothing edits a constant in the source."""
    # Arrange / Act
    with override_settings(NARCOS_VERSION="v9.9.9"):
        context = version_stamp(request=None)

    # Assert
    assert context == {"narcos_version": "v9.9.9"}


def test_an_unstamped_build_says_dev_rather_than_lying():
    """A local run must not claim to be a release."""
    with override_settings(NARCOS_VERSION="dev"):
        assert version_stamp(request=None)["narcos_version"] == "dev"


def test_the_version_appears_on_the_page_a_user_would_photograph(client, django_user_model):
    """Any authenticated screen carries it — support gets one photo, not a tour."""
    # Arrange
    user = django_user_model.objects.create_user(
        username="clerk", password="pw-for-test", role="EMPLOYEE"
    )
    client.force_login(user)

    # Act
    with override_settings(NARCOS_VERSION="v1.2.0"):
        response = client.get(reverse("dashboard"))

    # Assert
    assert response.status_code == 200
    assert "v1.2.0" in response.content.decode()


def test_the_login_screen_carries_it_too(client):
    """A machine that cannot get past login still has to be identifiable."""
    with override_settings(NARCOS_VERSION="v1.2.0"):
        response = client.get(reverse("login"))

    assert response.status_code == 200
    assert "v1.2.0" in response.content.decode()
