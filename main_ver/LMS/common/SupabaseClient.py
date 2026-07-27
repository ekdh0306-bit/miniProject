import os

from supabase import Client, create_client


class SupabaseConfigurationError(RuntimeError):
    """Raised when the server-side Supabase configuration is incomplete."""


def _required_environment(name):
    value = (os.environ.get(name) or "").strip()
    if name == "SUPABASE_PUBLISHABLE_KEY" and "sb_publishable_" in value:
        value = value[value.rfind("sb_publishable_"):]
    if name == "SUPABASE_SECRET_KEY" and "sb_secret_" in value:
        value = value[value.rfind("sb_secret_"):]
    duplicate_prefix = f"{name}="
    while value.startswith(duplicate_prefix):
        value = value[len(duplicate_prefix):].strip()
    if not value:
        raise SupabaseConfigurationError(
            f"서버 환경변수 {name} 설정이 필요합니다."
        )
    return value


def _supabase_base_url():
    url = _required_environment("SUPABASE_URL").strip().rstrip("/")
    if url.endswith("/rest/v1"):
        url = url[:-len("/rest/v1")]
    return url


def create_public_client() -> Client:
    """Create an isolated Auth client for one request."""
    return create_client(
        _supabase_base_url(),
        _required_environment("SUPABASE_PUBLISHABLE_KEY"),
    )


def create_admin_client() -> Client:
    """Create a server-only client used for private profile lookups."""
    server_key = (
        os.environ.get("SUPABASE_SECRET_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )
    if not server_key:
        raise SupabaseConfigurationError(
            "서버 환경변수 SUPABASE_SECRET_KEY 또는 "
            "SUPABASE_SERVICE_ROLE_KEY 설정이 필요합니다."
        )
    return create_client(
        _supabase_base_url(),
        server_key,
    )
