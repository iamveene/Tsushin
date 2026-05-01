"""Unit tests for install.py SSL/TLS logic.

Covers the three high-risk areas in the installer:
  1. Self-signed SAN branching (IP vs DNS) — the historical bug that broke
     IP-address installs such as the Parallels VM at 10.211.55.5.
  2. Manual cert pair validation (match, expiry, domain coverage, chain).
  3. Caddyfile generation for letsencrypt staging vs production and for
     self-signed SNI when the domain is an IP literal.

The installer is at the repo root, not under backend/, so path injection is
required. Tests avoid any Docker/network dependencies.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import ipaddress
import os
import sys
from pathlib import Path
from typing import Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# `install.py` lives at the host repo root, not inside the backend container.
# When pytest runs inside the container (REPO_ROOT resolves to "/"), the file
# isn't present — skip the whole module cleanly instead of crashing collection.
_INSTALL_PATH = REPO_ROOT / "install.py"
if not _INSTALL_PATH.is_file():
    pytest.skip(
        f"install.py not found at {_INSTALL_PATH}; this test runs only at the host "
        "repo root, not inside the backend container.",
        allow_module_level=True,
    )

# platform_utils is a sibling of install.py and is imported at module load.
_spec = importlib.util.spec_from_file_location("install", _INSTALL_PATH)
install = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(install)  # type: ignore[union-attr]

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def installer():
    """Installer with no args parsed; config is a blank dict."""
    ns = argparse.Namespace(
        defaults=False, http=False, domain=None, email=None,
        le_staging=False, port=8081, frontend_port=3030,
    )
    inst = install.TsushinInstaller(args=ns)
    return inst


def _gen_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _build_cert(
    subject_cn: str,
    *,
    san_dns: Optional[list] = None,
    san_ip: Optional[list] = None,
    not_before: Optional[_dt.datetime] = None,
    not_after: Optional[_dt.datetime] = None,
    issuer_cn: Optional[str] = None,
    key=None,
    issuer_key=None,
):
    """Generate a self-signed (or CA-signed) x509 cert for testing."""
    key = key or _gen_key()
    issuer_key = issuer_key or key
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject_cn)])
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn or subject_cn)])
    now = _dt.datetime.now(_dt.timezone.utc)
    nb = not_before or (now - _dt.timezone.utc.utcoffset(now) if False else (now - _dt.timedelta(days=1)))
    na = not_after or (now + _dt.timedelta(days=365))

    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(nb.replace(tzinfo=None) if nb.tzinfo else nb)
        .not_valid_after(na.replace(tzinfo=None) if na.tzinfo else na)
    )
    san_entries = []
    for d in (san_dns or []):
        san_entries.append(x509.DNSName(d))
    for i in (san_ip or []):
        san_entries.append(x509.IPAddress(ipaddress.ip_address(i)))
    if san_entries:
        builder = builder.add_extension(x509.SubjectAlternativeName(san_entries), critical=False)

    cert = builder.sign(private_key=issuer_key, algorithm=hashes.SHA256())
    return cert, key


def _write_pem(path: Path, cert, key=None):
    if cert is not None:
        path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    if key is not None:
        path.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )


# ---------------------------------------------------------------------------
# _is_ip helper (regression safety for the SAN branch)
# ---------------------------------------------------------------------------

def test_is_ip_recognizes_ipv4(installer):
    assert installer._is_ip("10.211.55.5") is True
    assert installer._is_ip("127.0.0.1") is True


def test_is_ip_recognizes_ipv6(installer):
    assert installer._is_ip("::1") is True
    assert installer._is_ip("2001:db8::1") is True


def test_is_ip_rejects_hostnames(installer):
    assert installer._is_ip("localhost") is False
    assert installer._is_ip("tsushin.example.com") is False
    assert installer._is_ip("") is False


# ---------------------------------------------------------------------------
# Self-signed SAN argument (the 10.211.55.5 bug)
# ---------------------------------------------------------------------------

class _RunRecorder:
    """Stands in for subprocess.run and captures the argv of the openssl call."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv, *args, **kwargs):
        self.calls.append(argv)
        class _R:
            returncode = 0
            stderr = ""
        return _R()


def test_selfsigned_ip_domain_emits_ip_san(installer, tmp_path, monkeypatch):
    installer.root_dir = tmp_path
    installer.config['SSL_MODE'] = 'selfsigned'
    installer.config['SSL_DOMAIN'] = '10.211.55.5'
    installer.config['TSN_STACK_NAME'] = 'tsushin'

    recorder = _RunRecorder()
    # subprocess.run is called for: openssl version (returncode must pass),
    # then for the cert generation; our recorder returns returncode=0 always.
    monkeypatch.setattr(install.subprocess, "run", recorder)

    installer.generate_self_signed_cert()

    # Find the req -x509 call
    req_calls = [c for c in recorder.calls if "-x509" in c]
    assert req_calls, "openssl req -x509 was not invoked"
    argv = req_calls[0]
    # Locate the value after -addext
    idx = argv.index("-addext")
    san = argv[idx + 1]
    assert san.startswith("subjectAltName="), san
    assert "IP:10.211.55.5" in san, san
    # Must NOT use DNS: for the IP literal
    assert "DNS:10.211.55.5" not in san, san
    # Loopback entries still present
    assert "IP:127.0.0.1" in san
    assert "IP:::1" in san


def test_selfsigned_hostname_domain_emits_dns_san(installer, tmp_path, monkeypatch):
    installer.root_dir = tmp_path
    installer.config['SSL_MODE'] = 'selfsigned'
    installer.config['SSL_DOMAIN'] = 'tsushin.local'
    installer.config['TSN_STACK_NAME'] = 'tsushin'

    recorder = _RunRecorder()
    monkeypatch.setattr(install.subprocess, "run", recorder)

    installer.generate_self_signed_cert()
    argv = [c for c in recorder.calls if "-x509" in c][0]
    san = argv[argv.index("-addext") + 1]
    assert "DNS:tsushin.local" in san
    assert "IP:tsushin.local" not in san


# ---------------------------------------------------------------------------
# Caddyfile generation
# ---------------------------------------------------------------------------

def test_caddyfile_selfsigned_ip_uses_port_only_explicit_cert(installer, tmp_path):
    installer.root_dir = tmp_path
    installer.config['SSL_MODE'] = 'selfsigned'
    installer.config['SSL_DOMAIN'] = '10.211.55.5'
    installer.config['TSN_STACK_NAME'] = 'tsushin'
    certs_dir = tmp_path / "caddy" / "tsushin" / "certs"
    certs_dir.mkdir(parents=True)
    (certs_dir / "selfsigned.crt").write_text("test cert")

    installer.generate_caddyfile()
    caddyfile = (tmp_path / "caddy" / "tsushin" / "Caddyfile").read_text()
    # Caddy rejects IP SNI and clients omit SNI for IP literals. Use a
    # port-only matcher with the installer-generated IP-SAN cert instead.
    assert "default_sni localhost" not in caddyfile
    assert "default_sni 10.211.55.5" not in caddyfile
    assert ":443 {" in caddyfile
    assert "10.211.55.5 {" not in caddyfile
    assert "tls /etc/caddy/certs/selfsigned.crt /etc/caddy/certs/selfsigned.key" in caddyfile
    assert "handle /tsushin-selfsigned-ca.pem" in caddyfile

    bootstrap = tmp_path / "caddy" / "tsushin" / "beacon-selfsigned-bootstrap.sh"
    assert bootstrap.exists()
    assert "REQUESTS_CA_BUNDLE" in bootstrap.read_text()


def test_caddyfile_selfsigned_hostname_uses_hostname_sni(installer, tmp_path):
    installer.root_dir = tmp_path
    installer.config['SSL_MODE'] = 'selfsigned'
    installer.config['SSL_DOMAIN'] = 'tsushin.local'
    installer.config['TSN_STACK_NAME'] = 'tsushin'
    certs_dir = tmp_path / "caddy" / "tsushin" / "certs"
    certs_dir.mkdir(parents=True)
    (certs_dir / "selfsigned.crt").write_text("test cert")

    installer.generate_caddyfile()
    caddyfile = (tmp_path / "caddy" / "tsushin" / "Caddyfile").read_text()
    assert "default_sni tsushin.local" in caddyfile
    assert "tls /etc/caddy/certs/selfsigned.crt /etc/caddy/certs/selfsigned.key" in caddyfile
    assert "handle /tsushin-selfsigned-ca.pem" in caddyfile


def test_caddyfile_letsencrypt_production_has_no_acme_ca(installer, tmp_path):
    installer.root_dir = tmp_path
    installer.config['SSL_MODE'] = 'letsencrypt'
    installer.config['SSL_DOMAIN'] = 'app.example.com'
    installer.config['SSL_EMAIL'] = 'admin@example.com'
    installer.config['TSN_STACK_NAME'] = 'tsushin'

    installer.generate_caddyfile()
    caddyfile = (tmp_path / "caddy" / "tsushin" / "Caddyfile").read_text()
    assert "email admin@example.com" in caddyfile
    assert "acme_ca" not in caddyfile


def test_caddyfile_letsencrypt_staging_emits_acme_ca(installer, tmp_path):
    installer.root_dir = tmp_path
    installer.config['SSL_MODE'] = 'letsencrypt'
    installer.config['SSL_DOMAIN'] = 'app.example.com'
    installer.config['SSL_EMAIL'] = 'admin@example.com'
    installer.config['SSL_LE_STAGING'] = 'true'
    installer.config['TSN_STACK_NAME'] = 'tsushin'

    installer.generate_caddyfile()
    caddyfile = (tmp_path / "caddy" / "tsushin" / "Caddyfile").read_text()
    assert "acme_ca https://acme-staging-v02.api.letsencrypt.org/directory" in caddyfile


def test_helper_image_refs_are_legacy_for_default_stack(installer):
    installer.config['TSN_STACK_NAME'] = 'tsushin'
    assert installer._get_helper_image_refs() == {
        "whatsapp_mcp": "tsushin/whatsapp-mcp:latest",
        "toolbox": "tsushin-toolbox:base",
    }


def test_helper_image_refs_are_stack_scoped_for_custom_stack(installer):
    installer.config['TSN_STACK_NAME'] = 'Audit_5.Local'
    assert installer._get_helper_image_refs() == {
        "whatsapp_mcp": "audit_5-local/whatsapp-mcp:latest",
        "toolbox": "audit_5-local/toolbox:base",
    }


def test_generated_env_includes_stack_scoped_helper_images(installer, tmp_path):
    installer.root_dir = tmp_path
    installer.env_file = tmp_path / ".env"
    installer.backend_data_dir = tmp_path / "backend" / "data"
    installer.config.update({
        'TSN_STACK_NAME': 'audit5local',
        'TSN_APP_PORT': '8091',
        'FRONTEND_PORT': '3091',
        'SSL_MODE': 'disabled',
        'ACCESS_TYPE': 'localhost',
        'PUBLIC_HOST': 'localhost',
    })

    installer.generate_env_file()
    env_text = installer.env_file.read_text()
    assert "TSN_WHATSAPP_MCP_IMAGE=audit5local/whatsapp-mcp:latest" in env_text
    assert "TSN_TOOLBOX_BASE_IMAGE=audit5local/toolbox:base" in env_text


# ---------------------------------------------------------------------------
# _validate_cert_pair
# ---------------------------------------------------------------------------

def test_validate_cert_pair_valid_hostname(installer, tmp_path):
    cert, key = _build_cert("example.com", san_dns=["example.com"])
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    _write_pem(cert_path, cert)
    _write_pem(key_path, None, key)

    ok, errors, warnings = installer._validate_cert_pair(
        cert_path=cert_path, key_path=key_path,
        chain_path=None, domain="example.com",
    )
    assert ok, f"errors={errors} warnings={warnings}"
    assert not errors


def test_validate_cert_pair_valid_ip_san(installer, tmp_path):
    cert, key = _build_cert("10.211.55.5", san_ip=["10.211.55.5"])
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    _write_pem(cert_path, cert)
    _write_pem(key_path, None, key)

    ok, errors, warnings = installer._validate_cert_pair(
        cert_path=cert_path, key_path=key_path,
        chain_path=None, domain="10.211.55.5",
    )
    assert ok, f"errors={errors} warnings={warnings}"


def test_validate_cert_pair_detects_key_mismatch(installer, tmp_path):
    cert, _key1 = _build_cert("example.com", san_dns=["example.com"])
    _key2 = _gen_key()
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    _write_pem(cert_path, cert)
    _write_pem(key_path, None, _key2)

    ok, errors, _ = installer._validate_cert_pair(
        cert_path=cert_path, key_path=key_path,
        chain_path=None, domain="example.com",
    )
    assert not ok
    assert any("do not match" in e.lower() for e in errors)


def test_validate_cert_pair_detects_expired_cert(installer, tmp_path):
    now = _dt.datetime.now(_dt.timezone.utc)
    cert, key = _build_cert(
        "example.com",
        san_dns=["example.com"],
        not_before=now - _dt.timedelta(days=400),
        not_after=now - _dt.timedelta(days=1),
    )
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    _write_pem(cert_path, cert)
    _write_pem(key_path, None, key)

    ok, errors, _ = installer._validate_cert_pair(
        cert_path=cert_path, key_path=key_path,
        chain_path=None, domain="example.com",
    )
    assert not ok
    assert any("expired" in e.lower() for e in errors)


def test_validate_cert_pair_warns_on_near_expiry(installer, tmp_path):
    now = _dt.datetime.now(_dt.timezone.utc)
    cert, key = _build_cert(
        "example.com",
        san_dns=["example.com"],
        not_before=now - _dt.timedelta(days=300),
        not_after=now + _dt.timedelta(days=10),
    )
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    _write_pem(cert_path, cert)
    _write_pem(key_path, None, key)

    ok, errors, warnings = installer._validate_cert_pair(
        cert_path=cert_path, key_path=key_path,
        chain_path=None, domain="example.com",
    )
    assert ok
    assert any("expires in less than 30 days" in w for w in warnings), warnings


def test_validate_cert_pair_domain_mismatch_hard_fails_when_declined(installer, tmp_path, monkeypatch):
    cert, key = _build_cert("other.example.com", san_dns=["other.example.com"])
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    _write_pem(cert_path, cert)
    _write_pem(key_path, None, key)

    # Decline the confirm prompt
    monkeypatch.setattr(install, "safe_input", lambda _prompt: "n")

    ok, errors, warnings = installer._validate_cert_pair(
        cert_path=cert_path, key_path=key_path,
        chain_path=None, domain="example.com",
    )
    assert not ok
    assert any("declined" in e.lower() or "domain-mismatched" in e.lower() for e in errors)


def test_validate_cert_pair_domain_mismatch_passes_when_accepted(installer, tmp_path, monkeypatch):
    cert, key = _build_cert("other.example.com", san_dns=["other.example.com"])
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    _write_pem(cert_path, cert)
    _write_pem(key_path, None, key)

    monkeypatch.setattr(install, "safe_input", lambda _prompt: "y")

    ok, errors, warnings = installer._validate_cert_pair(
        cert_path=cert_path, key_path=key_path,
        chain_path=None, domain="example.com",
    )
    assert ok, f"errors={errors}"
    assert any("does not cover" in w for w in warnings)


def test_validate_cert_pair_with_valid_chain(installer, tmp_path):
    # Generate a CA, then issue a leaf signed by the CA.
    ca_key = _gen_key()
    ca_cert, _ = _build_cert("Test CA", key=ca_key)
    leaf_key = _gen_key()
    leaf_cert, _ = _build_cert(
        "example.com", san_dns=["example.com"],
        key=leaf_key, issuer_cn="Test CA", issuer_key=ca_key,
    )

    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    chain_path = tmp_path / "chain.pem"
    _write_pem(cert_path, leaf_cert)
    _write_pem(key_path, None, leaf_key)
    chain_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))

    ok, errors, _ = installer._validate_cert_pair(
        cert_path=cert_path, key_path=key_path,
        chain_path=chain_path, domain="example.com",
    )
    assert ok, f"errors={errors}"


def test_validate_cert_pair_bad_chain_file_errors(installer, tmp_path):
    cert, key = _build_cert("example.com", san_dns=["example.com"])
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    chain_path = tmp_path / "chain.pem"
    _write_pem(cert_path, cert)
    _write_pem(key_path, None, key)
    chain_path.write_text("this is not a valid PEM block")

    ok, errors, _ = installer._validate_cert_pair(
        cert_path=cert_path, key_path=key_path,
        chain_path=chain_path, domain="example.com",
    )
    assert not ok
    assert any("chain" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Stale-IP self-signed cert detection (one-time migration for pre-fix installs)
# ---------------------------------------------------------------------------

def test_has_stale_ip_dns_san_detects_old_cert(installer, tmp_path):
    """A pre-fix cert encoding '10.211.55.5' as DNSName should be flagged."""
    # Build a cert that REPRODUCES the bug: IP literal in a DNSName SAN slot.
    cert, _key = _build_cert(
        "10.211.55.5",
        san_dns=["10.211.55.5", "localhost"],
    )
    cert_path = tmp_path / "selfsigned.crt"
    _write_pem(cert_path, cert)
    assert installer._has_stale_ip_dns_san(cert_path, "10.211.55.5") is True


def test_has_stale_ip_dns_san_accepts_correct_cert(installer, tmp_path):
    """A post-fix cert encoding the IP as IPAddress SAN should NOT be flagged."""
    cert, _key = _build_cert(
        "10.211.55.5",
        san_dns=["localhost"],
        san_ip=["10.211.55.5", "127.0.0.1"],
    )
    cert_path = tmp_path / "selfsigned.crt"
    _write_pem(cert_path, cert)
    assert installer._has_stale_ip_dns_san(cert_path, "10.211.55.5") is False


def test_has_stale_ip_dns_san_ignores_hostname_cert(installer, tmp_path):
    """Hostname certs must never be flagged for regeneration."""
    cert, _key = _build_cert("tsushin.local", san_dns=["tsushin.local"])
    cert_path = tmp_path / "selfsigned.crt"
    _write_pem(cert_path, cert)
    # Query with a hostname — should not trip.
    assert installer._has_stale_ip_dns_san(cert_path, "tsushin.local") is False


def test_generate_self_signed_cert_regenerates_stale_ip_cert(installer, tmp_path, monkeypatch):
    """Re-run on an install affected by the DNS-for-IP bug deletes and regenerates."""
    installer.root_dir = tmp_path
    installer.config['SSL_MODE'] = 'selfsigned'
    installer.config['SSL_DOMAIN'] = '10.211.55.5'
    installer.config['TSN_STACK_NAME'] = 'tsushin'

    certs_dir = tmp_path / "caddy" / "tsushin" / "certs"
    certs_dir.mkdir(parents=True)
    stale_cert, stale_key = _build_cert(
        "10.211.55.5",
        san_dns=["10.211.55.5", "localhost"],
    )
    cert_path = certs_dir / "selfsigned.crt"
    key_path = certs_dir / "selfsigned.key"
    _write_pem(cert_path, stale_cert)
    _write_pem(key_path, None, stale_key)
    old_cert_bytes = cert_path.read_bytes()

    recorder = _RunRecorder()
    monkeypatch.setattr(install.subprocess, "run", recorder)

    installer.generate_self_signed_cert()

    # The recorder stubs subprocess, so the openssl req call was captured but
    # did not actually write a new cert. The important assertion is: the stale
    # cert was detected and the unlink path was taken, so openssl req was
    # invoked (meaning the skip branch was bypassed). Without the migration,
    # the function would return at the "already exist" branch without calling
    # subprocess at all.
    req_calls = [c for c in recorder.calls if "-x509" in c]
    assert req_calls, "Installer did not attempt regeneration for a stale IP-SAN cert"
    # Sanity: the new argv emits IP: SAN, not DNS:
    argv = req_calls[0]
    san = argv[argv.index("-addext") + 1]
    assert "IP:10.211.55.5" in san
    assert "DNS:10.211.55.5" not in san
