"""D83: production settings for the on-prem Docker deployment.

CSRF_TRUSTED_ORIGINS must be derivable from ALLOWED_HOSTS (so setting the
static IP in one place is enough) with an explicit override, and the
proxy/HTTPS hardening must stay OFF by default — the on-prem stack serves
plain HTTP directly, where trusting a client-settable scheme header or
forcing secure-only cookies would break login.
"""

import importlib
import os
from unittest import mock

import pytest

import narcos.settings as narcos_settings


@pytest.fixture(autouse=True)
def _restore_settings_module():
    """Each test reloads the settings module under a patched env; put it back."""
    yield
    importlib.reload(narcos_settings)


def _reload(**env):
    with mock.patch.dict(os.environ, env, clear=False):
        return importlib.reload(narcos_settings)


def test_csrf_origins_derive_from_allowed_hosts():
    m = _reload(NARCOS_ALLOWED_HOSTS="192.168.1.50")
    assert "http://192.168.1.50" in m.CSRF_TRUSTED_ORIGINS
    # https too, so a future TLS proxy needs no settings change.
    assert "https://192.168.1.50" in m.CSRF_TRUSTED_ORIGINS


def test_csrf_origins_default_covers_localhost():
    m = _reload()  # dev default ALLOWED_HOSTS = localhost,127.0.0.1
    assert "http://localhost" in m.CSRF_TRUSTED_ORIGINS
    assert "http://127.0.0.1" in m.CSRF_TRUSTED_ORIGINS


def test_explicit_csrf_env_overrides_derivation():
    m = _reload(NARCOS_CSRF_TRUSTED_ORIGINS="http://erp.local, http://192.168.1.50")
    assert m.CSRF_TRUSTED_ORIGINS == ["http://erp.local", "http://192.168.1.50"]


def test_wildcard_host_is_not_turned_into_an_origin():
    m = _reload(NARCOS_ALLOWED_HOSTS="*,192.168.1.50")
    assert not any("*" in origin for origin in m.CSRF_TRUSTED_ORIGINS)
    assert "http://192.168.1.50" in m.CSRF_TRUSTED_ORIGINS


def test_proxy_and_secure_cookies_off_by_default():
    """Plain-HTTP LAN: no proxy header trust, no HTTPS-only cookies (would break login)."""
    m = _reload()
    assert getattr(m, "SECURE_PROXY_SSL_HEADER", None) is None
    assert getattr(m, "SESSION_COOKIE_SECURE", False) is False
    assert getattr(m, "CSRF_COOKIE_SECURE", False) is False


def test_tls_proxy_flag_enables_proxy_header_and_secure_cookies():
    m = _reload(NARCOS_BEHIND_TLS_PROXY="1")
    assert m.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert m.SESSION_COOKIE_SECURE is True
    assert m.CSRF_COOKIE_SECURE is True
