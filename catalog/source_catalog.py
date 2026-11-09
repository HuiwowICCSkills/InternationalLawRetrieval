"""Canonical source catalog for international-law retrieval.

This module owns the source IDs, display names, descriptions, grouping and
default enablement. The source-control console is only a state editor and must
not duplicate this metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterator


CATALOG_PATH = Path(__file__).with_name("source-catalog.json")


class CatalogError(ValueError):
    """Raised when the source catalog is missing or malformed."""


def _expect_string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"{where} must be a non-empty string")
    return value


def validate_catalog(data: Any) -> dict[str, Any]:
    """Validate the catalog structure and return it unchanged."""
    if not isinstance(data, dict):
        raise CatalogError("catalog root must be an object")
    if data.get("schema_version") != 1:
        raise CatalogError("schema_version must be 1")
    _expect_string(data.get("catalog_id"), "catalog_id")

    groups = data.get("groups")
    if not isinstance(groups, list) or not groups:
        raise CatalogError("groups must be a non-empty array")

    group_ids: set[str] = set()
    item_ids: set[str] = set()
    for group_index, group in enumerate(groups):
        where = f"groups[{group_index}]"
        if not isinstance(group, dict):
            raise CatalogError(f"{where} must be an object")
        group_id = _expect_string(group.get("id"), f"{where}.id")
        if group_id in group_ids:
            raise CatalogError(f"duplicate group id: {group_id}")
        group_ids.add(group_id)
        _expect_string(group.get("title"), f"{where}.title")
        _expect_string(group.get("icon"), f"{where}.icon")
        _expect_string(group.get("description"), f"{where}.description")

        items = group.get("items")
        if not isinstance(items, list) or not items:
            raise CatalogError(f"{where}.items must be a non-empty array")
        for item_index, item in enumerate(items):
            item_where = f"{where}.items[{item_index}]"
            if not isinstance(item, dict):
                raise CatalogError(f"{item_where} must be an object")
            item_id = _expect_string(item.get("id"), f"{item_where}.id")
            if item_id in item_ids:
                raise CatalogError(f"duplicate source id: {item_id}")
            item_ids.add(item_id)
            _expect_string(item.get("name"), f"{item_where}.name")
            _expect_string(item.get("description"), f"{item_where}.description")

            tags = item.get("tags")
            if not isinstance(tags, list) or any(
                not isinstance(tag, str) or not tag.strip() for tag in tags
            ):
                raise CatalogError(f"{item_where}.tags must be an array of strings")
            if not isinstance(item.get("default_enabled"), bool):
                raise CatalogError(f"{item_where}.default_enabled must be boolean")

    return data


def load_catalog(path: Path | str | None = None) -> dict[str, Any]:
    """Load and validate the catalog from disk."""
    catalog_path = Path(path) if path is not None else CATALOG_PATH
    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CatalogError(f"catalog not found: {catalog_path}") from exc
    except json.JSONDecodeError as exc:
        raise CatalogError(f"invalid JSON in {catalog_path}: {exc}") from exc
    return validate_catalog(payload)


def iter_items(catalog: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield (group_id, item) pairs in catalog order."""
    for group in catalog["groups"]:
        for item in group["items"]:
            yield group["id"], item


def default_sources(catalog: dict[str, Any]) -> dict[str, bool]:
    """Return the catalog's default state keyed by source ID."""
    return {item["id"]: item["default_enabled"] for _, item in iter_items(catalog)}


def catalog_fingerprint(catalog: dict[str, Any]) -> str:
    """Return a stable SHA-256 of the catalog's semantic content."""
    canonical = json.dumps(
        catalog,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("validate", "list", "defaults"),
        help="validate the catalog, list all sources, or print default state",
    )
    parser.add_argument("--path", type=Path, default=CATALOG_PATH)
    args = parser.parse_args()

    try:
        catalog = load_catalog(args.path)
    except CatalogError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.command == "validate":
        groups, items = len(catalog["groups"]), sum(
            1 for _ in iter_items(catalog)
        )
        print(f"OK groups={groups} items={items} sha256={catalog_fingerprint(catalog)}")
    elif args.command == "defaults":
        print(
            json.dumps(
                default_sources(catalog),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        rows = [
            {
                "group": group_id,
                "id": item["id"],
                "name": item["name"],
                "description": item["description"],
                "tags": item["tags"],
                "default_enabled": item["default_enabled"],
            }
            for group_id, item in iter_items(catalog)
        ]
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
