"""Curation / filtering / export logic for Entity Data Exporter.

The core idea: Home Assistant already classifies most "junk" for you in the
entity registry. Rather than maintaining a blocklist of attribute names, we
lean on:

  * entity_category == DIAGNOSTIC / CONFIG  -> dropped by default
  * hidden_by set                            -> dropped by default
  * disabled_by set                          -> dropped by default

On top of that automatic base you can still pass manual overrides
(exclude_entities, exclude_attributes) for the odd case the registry does
not catch.
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.util import slugify

from .const import (
    ATTR_AREAS,
    ATTR_DOMAINS,
    ATTR_EXCLUDE_ATTRIBUTES,
    ATTR_EXCLUDE_ENTITIES,
    ATTR_FORMAT,
    ATTR_INCLUDE_ALL_ATTRIBUTES,
    ATTR_INCLUDE_ATTRIBUTES,
    ATTR_INCLUDE_AUTOMATIONS,
    ATTR_INCLUDE_DIAGNOSTIC,
    ATTR_INCLUDE_DISABLED,
    ATTR_INCLUDE_HIDDEN,
    ATTR_INCLUDE_SCENES,
    ATTR_INCLUDE_SCRIPTS,
    ATTR_SCOPE,
    ATTR_WRITE_FILE,
    CSV_COLUMNS,
    DEFAULT_NOISE_ATTRIBUTES,
    FORMAT_CSV,
    FORMAT_JSON,
)

_LOGGER = logging.getLogger(__name__)


def _resolve_area_filter(
    area_reg: ar.AreaRegistry, requested: list[str] | None
) -> set[str] | None:
    """Turn a list of area ids or friendly names into a set of area ids.

    Returns None when no area filter was requested (meaning: all areas).
    """
    if not requested:
        return None

    # Build lookup by id and by normalized name.
    by_id: dict[str, str] = {}
    by_name: dict[str, str] = {}
    for area in area_reg.async_list_areas():
        by_id[area.id] = area.id
        by_name[slugify(area.name)] = area.id

    resolved: set[str] = set()
    for item in requested:
        if item in by_id:
            resolved.add(item)
        elif slugify(item) in by_name:
            resolved.add(by_name[slugify(item)])
        else:
            _LOGGER.warning("Area '%s' not found; ignoring", item)
    return resolved


def _clean_attributes(
    attributes: dict[str, Any],
    exclude: set[str],
    include_only: set[str] | None,
) -> dict[str, Any]:
    """Strip noise attributes from an entity's attribute dict."""
    if include_only:
        return {k: v for k, v in attributes.items() if k in include_only}
    return {k: v for k, v in attributes.items() if k not in exclude}


def build_curated_list(
    hass: HomeAssistant,
    *,
    areas: list[str] | None = None,
    domains: list[str] | None = None,
    include_diagnostic: bool = False,
    include_hidden: bool = False,
    include_disabled: bool = False,
    exclude_attributes: list[str] | None = None,
    exclude_entities: list[str] | None = None,
    include_attributes: list[str] | None = None,
    include_all_attributes: bool = True,
) -> list[dict[str, Any]]:
    """Walk the entity registry and return a curated list of entities.

    This runs entirely on in-memory registries and state machine, so it is
    safe to call from the event loop (no blocking I/O).
    """
    area_reg = ar.async_get(hass)
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)

    area_filter = _resolve_area_filter(area_reg, areas)
    domain_filter = set(domains) if domains else None
    exclude_entity_set = set(exclude_entities or [])

    # By default keep every attribute (so an LLM sees the full picture); only
    # drop the built-in noise list when include_all_attributes is False. The
    # user's exclude_attributes always applies. An include_attributes allowlist
    # still takes precedence over both.
    if include_all_attributes:
        attr_exclude = set(exclude_attributes or [])
    else:
        attr_exclude = set(DEFAULT_NOISE_ATTRIBUTES) | set(exclude_attributes or [])
    attr_include_only = set(include_attributes) if include_attributes else None

    curated: list[dict[str, Any]] = []

    for entry in entity_reg.entities.values():
        # --- Registry-based auto filtering (the "drop the junk" part) ---
        if entry.disabled_by is not None and not include_disabled:
            continue
        if entry.hidden_by is not None and not include_hidden:
            continue
        if (
            entry.entity_category
            in (EntityCategory.DIAGNOSTIC, EntityCategory.CONFIG)
            and not include_diagnostic
        ):
            continue

        # --- Manual entity override ---
        if entry.entity_id in exclude_entity_set:
            continue

        # --- Domain filter ---
        domain = entry.domain
        if domain_filter is not None and domain not in domain_filter:
            continue

        # --- Resolve the area (entity override, else its device's area) ---
        area_id = entry.area_id
        device = None
        if entry.device_id:
            device = device_reg.async_get(entry.device_id)
            if area_id is None and device is not None:
                area_id = device.area_id

        # --- Area filter ---
        if area_filter is not None and area_id not in area_filter:
            continue

        area_name = None
        if area_id and (area := area_reg.async_get_area(area_id)):
            area_name = area.name

        # --- Pull the live state for the current value + attributes ---
        state_obj = hass.states.get(entry.entity_id)
        if state_obj is None:
            # Entity is registered but not currently providing a state.
            state_value = None
            raw_attributes: dict[str, Any] = {}
            friendly_name = entry.name or entry.original_name
            device_class = entry.device_class or entry.original_device_class
        else:
            state_value = state_obj.state
            raw_attributes = dict(state_obj.attributes)
            friendly_name = raw_attributes.get("friendly_name") or entry.name
            device_class = raw_attributes.get("device_class") or entry.device_class

        curated.append(
            {
                "entity_id": entry.entity_id,
                "name": friendly_name,
                "domain": domain,
                "area": area_name,
                "device": device.name_by_user or device.name if device else None,
                "device_class": device_class,
                "state": state_value,
                "attributes": _clean_attributes(
                    raw_attributes, attr_exclude, attr_include_only
                ),
            }
        )

    curated.sort(key=lambda e: (e["area"] or "~", e["domain"], e["entity_id"]))
    return curated


def _entity_area_id(
    entity_reg: er.EntityRegistry,
    device_reg: dr.DeviceRegistry,
    entity_id: str,
) -> str | None:
    """Resolve an entity_id to its area (entity override, else device area)."""
    entry = entity_reg.async_get(entity_id)
    if entry is None:
        return None
    if entry.area_id:
        return entry.area_id
    if entry.device_id:
        device = device_reg.async_get(entry.device_id)
        if device is not None:
            return device.area_id
    return None


def _effective_areas(
    entity_reg: er.EntityRegistry,
    device_reg: dr.DeviceRegistry,
    ref_entities: set[str],
    ref_devices: set[str],
    ref_areas: set[str],
) -> set[str]:
    """Resolve everything an item references down to a set of area ids.

    Combines directly-referenced areas with the areas of referenced devices
    and the areas of referenced entities. This is what makes a room-specific
    automation/script/scene match when that room is selected.
    """
    areas: set[str] = set(ref_areas)
    for device_id in ref_devices:
        device = device_reg.async_get(device_id)
        if device is not None and device.area_id:
            areas.add(device.area_id)
    for entity_id in ref_entities:
        area_id = _entity_area_id(entity_reg, device_reg, entity_id)
        if area_id:
            areas.add(area_id)
    return areas


def _scene_referenced_entities(hass: HomeAssistant, entity) -> set[str]:
    """Entities a scene controls (from its config, falling back to state)."""
    refs = set(getattr(entity, "referenced_entities", set()) or set())
    if refs:
        return refs
    state_obj = hass.states.get(entity.entity_id)
    if state_obj:
        return set(state_obj.attributes.get("entity_id", []) or [])
    return set()


def _scene_config(hass: HomeAssistant, entity) -> dict[str, Any] | None:
    """Best-effort raw config for a scene (target entity states)."""
    raw = getattr(entity, "raw_config", None)
    if isinstance(raw, dict):
        return raw
    scene_config = getattr(entity, "scene_config", None)
    if scene_config is None:
        return None
    states = getattr(scene_config, "states", {}) or {}
    entities: dict[str, Any] = {}
    for eid, state in states.items():
        try:
            entities[eid] = {
                "state": state.state,
                "attributes": dict(state.attributes),
            }
        except AttributeError:
            entities[eid] = state
    return {
        "name": getattr(scene_config, "name", None),
        "entities": entities,
    }


def build_logic_items(
    hass: HomeAssistant,
    domain: str,
    area_filter: set[str] | None,
) -> list[dict[str, Any]]:
    """Return automations / scripts / scenes with full config + references.

    `domain` is "automation", "script", or "scene". Each record carries the
    raw config plus the entities, devices, and resolved areas it references.
    When `area_filter` is set, only items that resolve into one of those areas
    are returned (room-specific matching); when it is None, all are returned.
    """
    component = hass.data.get(domain)
    if component is None:
        _LOGGER.debug("%s component not loaded; skipping", domain)
        return []

    entity_reg = er.async_get(hass)
    device_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)

    items: list[dict[str, Any]] = []
    for entity in getattr(component, "entities", []):
        if domain == "scene":
            ref_entities = _scene_referenced_entities(hass, entity)
            ref_devices: set[str] = set(
                getattr(entity, "referenced_devices", set()) or set()
            )
            ref_areas: set[str] = set(
                getattr(entity, "referenced_areas", set()) or set()
            )
            raw = _scene_config(hass, entity)
        else:
            ref_entities = set(
                getattr(entity, "referenced_entities", set()) or set()
            )
            ref_devices = set(
                getattr(entity, "referenced_devices", set()) or set()
            )
            ref_areas = set(
                getattr(entity, "referenced_areas", set()) or set()
            )
            raw = getattr(entity, "raw_config", None)

        eff_areas = _effective_areas(
            entity_reg, device_reg, ref_entities, ref_devices, ref_areas
        )

        # Area-aware filtering (containment): when rooms are selected, keep
        # only logic whose areas are FULLY within the selection. A house-wide
        # item that merely touches the selected room (e.g. a "smart plug
        # offline" alert spanning six areas) is excluded here and only appears
        # when you select all its areas or leave the area filter empty. An item
        # with no resolvable area is excluded while a filter is active.
        if area_filter is not None:
            if not eff_areas or not eff_areas.issubset(area_filter):
                continue

        state_obj = hass.states.get(entity.entity_id)
        alias = None
        mode = None
        if isinstance(raw, dict):
            alias = raw.get("alias") or raw.get("name")
            mode = raw.get("mode")

        area_names = sorted(
            (area_reg.async_get_area(a).name)
            for a in eff_areas
            if area_reg.async_get_area(a) is not None
        )

        record: dict[str, Any] = {
            "entity_id": entity.entity_id,
            "name": alias or (state_obj.name if state_obj else entity.entity_id),
            "id": getattr(entity, "unique_id", None),
            "state": state_obj.state if state_obj else None,
            "areas": area_names,
            "referenced_entities": sorted(ref_entities),
            "referenced_devices": sorted(ref_devices),
            "config": raw,
        }
        if domain == "automation":
            record["mode"] = mode or "single"
            record["last_triggered"] = (
                state_obj.attributes.get("last_triggered") if state_obj else None
            )
        elif domain == "script":
            record["mode"] = mode or "single"

        items.append(record)

    items.sort(key=lambda r: (r["name"] or r["entity_id"]).lower())
    return items


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    """Blocking file write — must be run in the executor."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)


def _csv_cell(value: Any) -> str:
    """Render a curated-entity value for a CSV cell.

    Scalars pass through as-is; dict/list values (notably ``attributes``) are
    JSON-encoded so the whole structure survives in a single column.
    """
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _write_csv_file(path: Path, entities: list[dict[str, Any]]) -> None:
    """Blocking write of the curated entity list as a flat CSV.

    One row per entity, columns per ``CSV_COLUMNS``. Attributes are JSON-encoded
    into a single ``attributes`` column so nothing is lost. Automations, scripts
    and scenes are nested structures and are not part of the CSV — use the JSON
    format for those. Must be run in the executor.
    """
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for entity in entities:
            writer.writerow([_csv_cell(entity.get(col)) for col in CSV_COLUMNS])


async def async_handle_export(hass: HomeAssistant, call: ServiceCall) -> dict:
    """Service entry point: build the list, optionally write it, return it."""
    data = call.data

    curated = build_curated_list(
        hass,
        areas=data.get(ATTR_AREAS),
        domains=data.get(ATTR_DOMAINS),
        include_diagnostic=data.get(ATTR_INCLUDE_DIAGNOSTIC, False),
        include_hidden=data.get(ATTR_INCLUDE_HIDDEN, False),
        include_disabled=data.get(ATTR_INCLUDE_DISABLED, False),
        exclude_attributes=data.get(ATTR_EXCLUDE_ATTRIBUTES),
        exclude_entities=data.get(ATTR_EXCLUDE_ENTITIES),
        include_attributes=data.get(ATTR_INCLUDE_ATTRIBUTES),
        include_all_attributes=data.get(ATTR_INCLUDE_ALL_ATTRIBUTES, True),
    )

    # Resolve the selected areas once so logic items match the same scope as
    # the entity list. None = no area filter (whole house / all).
    area_filter = _resolve_area_filter(ar.async_get(hass), data.get(ATTR_AREAS))

    include_automations = data.get(ATTR_INCLUDE_AUTOMATIONS, True)
    include_scripts = data.get(ATTR_INCLUDE_SCRIPTS, True)
    include_scenes = data.get(ATTR_INCLUDE_SCENES, True)

    automations = (
        build_logic_items(hass, "automation", area_filter)
        if include_automations
        else []
    )
    scripts = (
        build_logic_items(hass, "script", area_filter) if include_scripts else []
    )
    scenes = (
        build_logic_items(hass, "scene", area_filter) if include_scenes else []
    )

    scope = data.get(ATTR_SCOPE, "export")
    file_format = data.get(ATTR_FORMAT, FORMAT_JSON)
    payload: dict[str, Any] = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "scope": scope,
            "format": file_format,
            "entity_count": len(curated),
            "automation_count": len(automations),
            "script_count": len(scripts),
            "scene_count": len(scenes),
            "filters": {
                "areas": data.get(ATTR_AREAS) or "all",
                "domains": data.get(ATTR_DOMAINS) or "all",
                "include_diagnostic": data.get(ATTR_INCLUDE_DIAGNOSTIC, False),
                "include_hidden": data.get(ATTR_INCLUDE_HIDDEN, False),
                "include_disabled": data.get(ATTR_INCLUDE_DISABLED, False),
                "include_automations": include_automations,
                "include_scripts": include_scripts,
                "include_scenes": include_scenes,
                "include_all_attributes": data.get(
                    ATTR_INCLUDE_ALL_ATTRIBUTES, True
                ),
            },
            "description": (
                "Curated list of actionable HA entities plus existing "
                "automations, scripts, and scenes for LLM automation design. "
                "When areas are selected, logic is filtered to items that "
                "reference those areas."
            ),
        },
        "entities": curated,
        "automations": automations,
        "scripts": scripts,
        "scenes": scenes,
    }

    file_path: str | None = None
    if data.get(ATTR_WRITE_FILE, True):
        safe_scope = slugify(scope) or "export"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = "csv" if file_format == FORMAT_CSV else "json"
        filename = f"ha_entities_{safe_scope}_{stamp}.{ext}"
        target = Path(hass.config.path(filename))
        try:
            if file_format == FORMAT_CSV:
                # CSV covers the flat entity list only (automations/scripts/
                # scenes are nested — use JSON for those).
                await hass.async_add_executor_job(
                    _write_csv_file, target, curated
                )
            else:
                await hass.async_add_executor_job(
                    _write_json_file, target, payload
                )
            file_path = str(target)
            _LOGGER.info(
                "Entity Data Exporter: wrote %d entities to %s (%s)",
                len(curated),
                file_path,
                file_format,
            )
        except OSError as err:
            _LOGGER.error(
                "Entity Data Exporter: failed to write %s: %s", target, err
            )

    # Returned to the caller when `return_response: true` is used, and shown
    # in Developer Tools > Actions.
    return {
        "entity_count": len(curated),
        "automation_count": len(automations),
        "script_count": len(scripts),
        "scene_count": len(scenes),
        "format": file_format,
        "file_path": file_path,
        "metadata": payload["metadata"],
        "entities": curated,
        "automations": automations,
        "scripts": scripts,
        "scenes": scenes,
    }
