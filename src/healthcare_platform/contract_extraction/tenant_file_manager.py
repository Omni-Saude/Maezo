"""Tenant-isolated file manager for DMN overrides."""
import re
from pathlib import Path
from typing import List

_TENANT_ID_PATTERN = re.compile(r'^[a-z0-9_-]+$')
BASE_PATH = Path('healthcare_platform/shared/dmn/tenant_overrides')


def _validate_tenant_id(tenant_id: str) -> None:
    """Validate tenant_id to prevent path traversal."""
    if not _TENANT_ID_PATTERN.match(tenant_id):
        raise ValueError(f"Invalid tenant_id '{tenant_id}': must match [a-z0-9_-]+")


def _validate_segment(name: str, value: str) -> None:
    """Validate a path segment has no traversal characters."""
    if '..' in value or '/' in value or '\\' in value:
        raise ValueError(f"Invalid {name}: '{value}' contains path traversal")


class TenantFileManager:
    """Manages DMN files per tenant with path isolation."""

    def __init__(self, base_path: Path = BASE_PATH):
        self.base = base_path

    def _path(self, tenant_id: str, category: str, filename: str) -> Path:
        _validate_tenant_id(tenant_id)
        _validate_segment("category", category)
        _validate_segment("filename", filename)
        return self.base / tenant_id / category / filename

    def write_dmn(self, tenant_id: str, category: str, filename: str, xml_content: str) -> Path:
        """Write a DMN XML file for a tenant."""
        path = self._path(tenant_id, category, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(xml_content, encoding="utf-8")
        return path

    def read_dmn(self, tenant_id: str, category: str, filename: str) -> str:
        """Read a DMN XML file for a tenant."""
        return self._path(tenant_id, category, filename).read_text(encoding="utf-8")

    def list_tenant_dmns(self, tenant_id: str) -> List[Path]:
        """List all DMN files for a tenant."""
        _validate_tenant_id(tenant_id)
        tenant_dir = self.base / tenant_id
        return sorted(tenant_dir.rglob("*.dmn")) if tenant_dir.exists() else []

    def delete_dmn(self, tenant_id: str, category: str, filename: str) -> bool:
        """Delete a DMN file for a tenant. Returns True if deleted."""
        path = self._path(tenant_id, category, filename)
        if path.exists():
            path.unlink()
            return True
        return False
