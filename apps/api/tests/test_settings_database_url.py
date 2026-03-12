from __future__ import annotations

import os
from unittest.mock import patch

from django.test import SimpleTestCase

from config.settings import _database_config_from_url


class DatabaseUrlParsingTests(SimpleTestCase):
    def test_database_url_parses_credentials_host_port_and_options(self):
        config = _database_config_from_url(
            "postgres://db_user:p%40ss%2Fword@db.example.com:5433/construction_db?sslmode=require&target_session_attrs=read-write"
        )

        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "construction_db")
        self.assertEqual(config["USER"], "db_user")
        self.assertEqual(config["PASSWORD"], "p@ss/word")
        self.assertEqual(config["HOST"], "db.example.com")
        self.assertEqual(config["PORT"], "5433")
        self.assertEqual(
            config["OPTIONS"],
            {"sslmode": "require", "target_session_attrs": "read-write"},
        )

    def test_database_url_uses_fallback_env_when_credentials_missing(self):
        with patch.dict(
            os.environ,
            {
                "POSTGRES_USER": "fallback_user",
                "POSTGRES_PASSWORD": "fallback_pass",
                "POSTGRES_HOST": "fallback.host",
                "POSTGRES_PORT": "5440",
            },
            clear=False,
        ):
            config = _database_config_from_url("postgres:///fallback_db")

        self.assertEqual(config["NAME"], "fallback_db")
        self.assertEqual(config["USER"], "fallback_user")
        self.assertEqual(config["PASSWORD"], "fallback_pass")
        self.assertEqual(config["HOST"], "fallback.host")
        self.assertEqual(config["PORT"], "5440")

    def test_database_url_requires_postgres_scheme(self):
        with self.assertRaisesMessage(ValueError, "DATABASE_URL must be a PostgreSQL URL."):
            _database_config_from_url("mysql://user:pass@db.example.com:3306/app")

    def test_database_url_requires_database_name(self):
        with self.assertRaisesMessage(ValueError, "DATABASE_URL must include a database name."):
            _database_config_from_url("postgres://db_user:pass@db.example.com:5432")
