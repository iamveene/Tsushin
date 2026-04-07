import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from install import TsushinInstaller


def build_installer(**overrides):
    installer = TsushinInstaller(
        argparse.Namespace(
            defaults=False,
            http=False,
            domain=None,
            email=None,
            port=8081,
            frontend_port=3030,
        )
    )
    installer.config.update(
        {
            "TSN_APP_PORT": 8081,
            "FRONTEND_PORT": 3030,
            "SSL_MODE": "disabled",
            "SSL_DOMAIN": "localhost",
            "ACCESS_TYPE": "localhost",
            "PUBLIC_HOST": "localhost",
        }
    )
    installer.config.update(overrides)
    return installer


def test_local_health_checks_use_loopback_ip():
    installer = build_installer()

    assert installer._get_local_backend_health_url() == "http://127.0.0.1:8081/api/health"
    assert installer._get_local_frontend_health_url() == "http://127.0.0.1:3030"


def test_remote_http_access_urls_use_public_host():
    installer = build_installer(ACCESS_TYPE="remote", PUBLIC_HOST="10.211.55.5")

    urls = installer._get_access_urls()

    assert urls["primary"] == "http://10.211.55.5:3030"
    assert urls["frontend"] == "http://10.211.55.5:3030"
    assert urls["backend"] == "http://10.211.55.5:8081"


def test_ssl_access_url_prefers_ssl_domain():
    installer = build_installer(SSL_MODE="selfsigned", SSL_DOMAIN="localhost")

    urls = installer._get_access_urls()

    assert urls["primary"] == "https://localhost"
    assert urls["frontend"] == "http://localhost:3030"
    assert urls["backend"] == "http://localhost:8081"
