"""Swagger 2.0 -> OpenAPI 3.0.3 request-side contract migration library."""

from .converter import migrate, migrate_file

__all__ = ["migrate", "migrate_file"]
