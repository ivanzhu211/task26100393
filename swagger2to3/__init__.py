"""Swagger 2.0 -> OpenAPI 3.0.3 request-side contract migration library."""

from swagger2to3.migrate import migrate, migrate_file

__all__ = ["migrate", "migrate_file"]
__version__ = "0.1.0"
