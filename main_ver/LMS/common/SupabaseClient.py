import os

from supabase import Client, create_client


class SupabaseConfigurationError(RuntimeError):
    """Raised when the server-side Supabase configuration is incomplete."""


def _required_environment(name):
    value = os.environ.get(name)
    if not value:
        raise SupabaseConfigurationError(
            f"서버 환경변수 {name} 설정이 필요합니다."
        )
    return value


def create_public_client() -> Client:
    """Create an isolated Auth client for one request."""
    return create_client(
        _required_environment("SUPABASE_URL"),
        _required_environment("SUPABASE_PUBLISHABLE_KEY"),
    )


def create_admin_client() -> Client:
    """Create a server-only client used for private profile lookups."""
    return create_client(
        _required_environment("SUPABASE_URL"),
        _required_environment("SUPABASE_SERVICE_ROLE_KEY"),
    )
