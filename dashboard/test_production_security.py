import os
import runpy
import secrets
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse


class ProductionConfigurationTests(SimpleTestCase):
    def load_settings(self, **changes):
        environment = {
            "DJANGO_DEBUG": "false",
            "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
            "DJANGO_ALLOWED_HOSTS": "quotes.example.com",
        }
        environment.update(changes)
        with patch.dict(os.environ, environment, clear=True):
            return runpy.run_path(str(Path(settings.BASE_DIR) / "steel_quotes/settings.py"))

    def test_unsafe_production_configuration_fails_closed(self):
        for changes in (
            {"DJANGO_DEBUG": "tru"},
            {"DJANGO_SECRET_KEY": ""},
            {"DJANGO_SECRET_KEY": "short-secret"},
            {"DJANGO_SECRET_KEY": "a" * 60},
            {"DJANGO_SECRET_KEY": "django-insecure-" + secrets.token_urlsafe(50)},
            {"DJANGO_ALLOWED_HOSTS": ""},
            {"DJANGO_ALLOWED_HOSTS": " , "},
            {"DJANGO_ALLOWED_HOSTS": "*"},
            {"DJANGO_ALLOWED_HOSTS": ".example.com"},
            {"DJANGO_ALLOWED_HOSTS": "https://quotes.example.com"},
            {"DJANGO_ALLOWED_HOSTS": "quotes.example.com:443"},
            {"DJANGO_ALLOWED_HOSTS": "good.example,bad_host"},
        ):
            with self.subTest(fields=list(changes)), self.assertRaises(ImproperlyConfigured):
                self.load_settings(**changes)

    def test_valid_production_enables_security_controls(self):
        config = self.load_settings()
        for name in ("SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT",
                     "SESSION_COOKIE_HTTPONLY", "REQUIRE_STRONG_LOGIN_PASSWORDS"):
            self.assertTrue(config[name], name)
        self.assertFalse(config["DEBUG"])
        self.assertEqual(config["ALLOWED_HOSTS"], ["quotes.example.com"])
        self.assertEqual(config["SECURE_HSTS_SECONDS"], 3600)
        self.assertFalse(config["SECURE_HSTS_INCLUDE_SUBDOMAINS"])
        self.assertNotIn("SECURE_PROXY_SSL_HEADER", config)


class ProductionRequestTests(TestCase):
    def setUp(self):
        self.password = "Granite-River-Production-2047!"
        self.user = get_user_model().objects.create_user(username="production-owner", password=self.password)

    @override_settings(REQUIRE_STRONG_LOGIN_PASSWORDS=True)
    def test_existing_weak_accounts_cannot_log_in_until_password_is_changed(self):
        self.user.set_password("12345")
        self.user.save()
        for url in (reverse("login"), reverse("admin:login")):
            response = self.client.post(url, {"username": self.user.username, "password": "12345"})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("_auth_user_id", self.client.session)
        self.user.set_password(self.password)
        self.user.save()
        response = self.client.post(reverse("login"), {"username": self.user.username, "password": self.password})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))

    def test_forged_forwarding_headers_cannot_evade_pair_lockout(self):
        for index in range(5):
            response = self.client.post(reverse("login"), {
                "username": self.user.username, "password": "wrong",
            }, REMOTE_ADDR="198.51.100.10", HTTP_X_FORWARDED_FOR=f"203.0.113.{index + 1}")
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)
        other = get_user_model().objects.create_user(username="other-production-user", password=self.password)
        # Coworkers sharing an office IP must not inherit this user's lockout.
        response = Client().post(reverse("login"), {"username": other.username, "password": self.password},
                                 REMOTE_ADDR="198.51.100.10")
        self.assertEqual(response.status_code, 302)
        response = Client().post(reverse("login"), {"username": self.user.username, "password": self.password},
                                 REMOTE_ADDR="198.51.100.11")
        self.assertEqual(response.status_code, 302)

    def test_private_pages_and_logout_cannot_be_cached(self):
        self.client.force_login(self.user)
        for url in (reverse("dashboard:home"), reverse("dashboard:customer_list"), reverse("password_change")):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn("no-store", response["Cache-Control"])
            self.assertIn("private", response["Cache-Control"])
            self.assertEqual(response["Referrer-Policy"], "no-referrer")
        response = self.client.post(reverse("logout"))
        self.assertIn("no-store", response["Cache-Control"])
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(SECURE_SSL_REDIRECT=True, SESSION_COOKIE_SECURE=True,
                       CSRF_COOKIE_SECURE=True, SECURE_HSTS_SECONDS=3600)
    def test_https_cookies_and_cross_origin_csrf_rejection(self):
        client = Client(enforce_csrf_checks=True)
        url = reverse("login")
        response = client.get(url, HTTP_X_FORWARDED_PROTO="https")
        self.assertEqual(response.status_code, 301)
        response = client.get(url, secure=True)
        token = response.cookies[settings.CSRF_COOKIE_NAME].value
        self.assertTrue(response.cookies[settings.CSRF_COOKIE_NAME]["secure"])
        self.assertEqual(response["Strict-Transport-Security"], "max-age=3600")
        credentials = {"username": self.user.username, "password": self.password}
        response = client.post(url, credentials, secure=True, HTTP_X_CSRFTOKEN=token,
                               HTTP_ORIGIN="https://attacker.example")
        self.assertEqual(response.status_code, 403)
        response = client.post(url, credentials, secure=True, HTTP_X_CSRFTOKEN=token,
                               HTTP_ORIGIN="https://testserver")
        self.assertEqual(response.status_code, 302)
        cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertTrue(cookie["secure"])
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
