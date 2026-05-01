from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_frontend_internal_backend_urls_default_to_stack_scoped_names():
    compose = _read("docker-compose.yml")
    dockerfile = _read("frontend/Dockerfile")

    assert (
        "BACKEND_INTERNAL_URL=${BACKEND_INTERNAL_URL:-http://${TSN_STACK_NAME:-tsushin}-backend:8081}"
        in compose
    )
    assert (
        "INTERNAL_API_URL=${INTERNAL_API_URL:-http://${TSN_STACK_NAME:-tsushin}-backend:8081}"
        in compose
    )
    assert "BACKEND_INTERNAL_URL=${BACKEND_INTERNAL_URL:-http://backend:8081}" not in compose
    assert "TSN_STACK_NAME=${TSN_STACK_NAME:-tsushin}" in compose
    assert "ARG BACKEND_INTERNAL_URL=" in dockerfile
    assert "ENV BACKEND_INTERNAL_URL=${BACKEND_INTERNAL_URL}" in dockerfile
    assert "ARG TSN_STACK_NAME=tsushin" in dockerfile
    assert "ENV TSN_STACK_NAME=${TSN_STACK_NAME}" in dockerfile


def test_next_rewrite_fallback_uses_stack_name_when_present():
    next_config = _read("frontend/next.config.mjs")
    auth_proxy = _read("frontend/app/api/auth/[...path]/route.ts")

    assert "process.env.TSN_STACK_NAME" in next_config
    assert "`http://${stackName}-backend:8081`" in next_config
    assert "fallback: [" in next_config
    assert "process.env.TSN_STACK_NAME" in auth_proxy
    assert "`http://${stackName}-backend:8081`" in auth_proxy
    assert "process.env.TSN_SSL_MODE" in auth_proxy
    assert "return 'http'" in auth_proxy


def test_base_caddyfile_uses_stack_scoped_upstreams():
    caddyfile = _read("proxy/Caddyfile")

    assert "reverse_proxy {$TSN_STACK_NAME:tsushin}-backend:8081" in caddyfile
    assert "reverse_proxy {$TSN_STACK_NAME:tsushin}-frontend:3030" in caddyfile
    assert "reverse_proxy backend:8081" not in caddyfile
    assert "reverse_proxy frontend:3030" not in caddyfile
