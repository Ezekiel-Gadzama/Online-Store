"""Built-in store-type catalog templates for new-server product uploads."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

_DATA = Path(__file__).resolve().parent.parent / "data" / "store_templates"


@dataclass(frozen=True)
class StoreTemplate:
    template_id: str
    display_name: str
    store_types: List[str]
    catalog_path: Path

    def manifest(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "display_name": self.display_name,
            "store_types": list(self.store_types),
            "catalog_bundle": str(self.catalog_path.name),
        }

    def manifest_path(self) -> Path:
        return self.catalog_path.parent / "manifest.json"


DIGITAL = StoreTemplate(
    template_id="digital",
    display_name="Digital products (DBS)",
    store_types=["digital"],
    catalog_path=_DATA / "digital" / "catalog.json",
)

TEMPLATES: Dict[str, StoreTemplate] = {
    DIGITAL.template_id: DIGITAL,
}


def get_template(template_id: str) -> StoreTemplate:
    tid = template_id.strip().lower()
    if tid not in TEMPLATES:
        raise KeyError(f"Unknown store template {template_id!r}; choose from {list(TEMPLATES)}")
    return TEMPLATES[tid]


def template_for_store_types(store_types: List[str]) -> StoreTemplate | None:
    types = {t.strip().lower() for t in store_types if t}
    if "digital" in types:
        return DIGITAL
    return None