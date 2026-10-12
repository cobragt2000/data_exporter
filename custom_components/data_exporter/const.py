"""Constants and the service schema for Entity Data Exporter."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.helpers import config_validation as cv

DOMAIN = "data_exporter"
SERVICE_EXPORT_DATA = "export_data"

# Bump when the bundled card JS changes, so the resource URL's ?v= query
# busts the browser cache. Keep in sync with manifest.json "version".
CARD_VERSION = "2.4.4"

# Service call parameter names.
ATTR_AREAS = "areas"
ATTR_DOMAINS = "domains"
ATTR_INCLUDE_DIAGNOSTIC = "include_diagnostic"
ATTR_INCLUDE_HIDDEN = "include_hidden"
ATTR_INCLUDE_DISABLED = "include_disabled"
ATTR_INCLUDE_AUTOMATIONS = "include_automations"
ATTR_INCLUDE_SCRIPTS = "include_scripts"
ATTR_INCLUDE_SCENES = "include_scenes"
ATTR_EXCLUDE_ATTRIBUTES = "exclude_attributes"
ATTR_EXCLUDE_ENTITIES = "exclude_entities"
ATTR_INCLUDE_ATTRIBUTES = "include_attributes"
ATTR_INCLUDE_ALL_ATTRIBUTES = "include_all_attributes"
ATTR_WRITE_FILE = "write_file"
ATTR_SCOPE = "scope"
ATTR_FORMAT = "format"

# Written-file formats.
FORMAT_JSON = "json"
FORMAT_CSV = "csv"
FILE_FORMATS = [FORMAT_JSON, FORMAT_CSV]

# Column order for the CSV (flat) entity export.
CSV_COLUMNS = [
    "entity_id",
    "name",
    "domain",
    "area",
    "device",
    "device_class",
    "state",
    "attributes",
]

# Attributes that are almost always noise for LLM-driven automation design.
# These are stripped from an entity's attribute dict in addition to anything
# the user passes in `exclude_attributes`. They are NOT used to drop whole
# entities — only to clean each entity's attribute payload.
DEFAULT_NOISE_ATTRIBUTES: list[str] = [
    "rssi",
    "signal_strength",
    "linkquality",
    "voltage",
    "battery",
    "battery_level",
    "attribution",
    "icon",
    "entity_picture",
    "assumed_state",
    "restored",
    "supported_features",
    "supported_color_modes",
    "device_class",  # kept in the top-level record instead
    "friendly_name",  # kept in the top-level record instead
]

SERVICE_SCHEMA = vol.Schema(
    {
        # Area ids OR friendly area names; empty / omitted = all areas.
        vol.Optional(ATTR_AREAS): vol.All(cv.ensure_list, [cv.string]),
        # Domains such as light, switch, climate; empty / omitted = all safe
        # domains.
        vol.Optional(ATTR_DOMAINS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_INCLUDE_DIAGNOSTIC, default=False): cv.boolean,
        vol.Optional(ATTR_INCLUDE_HIDDEN, default=False): cv.boolean,
        vol.Optional(ATTR_INCLUDE_DISABLED, default=False): cv.boolean,
        # Include full automation configs (triggers/conditions/actions) plus
        # the entities/devices/areas each one references.
        vol.Optional(ATTR_INCLUDE_AUTOMATIONS, default=True): cv.boolean,
        vol.Optional(ATTR_INCLUDE_SCRIPTS, default=True): cv.boolean,
        vol.Optional(ATTR_INCLUDE_SCENES, default=True): cv.boolean,
        # Manual overrides.
        vol.Optional(ATTR_EXCLUDE_ATTRIBUTES): vol.All(
            cv.ensure_list, [cv.string]
        ),
        vol.Optional(ATTR_EXCLUDE_ENTITIES): vol.All(cv.ensure_list, [cv.string]),
        # If set, ONLY these attributes are kept per entity (allowlist mode).
        vol.Optional(ATTR_INCLUDE_ATTRIBUTES): vol.All(
            cv.ensure_list, [cv.string]
        ),
        # Default True: export every attribute an entity exposes so a downstream
        # LLM sees the full picture. Set False to strip the built-in noise list
        # (rssi, battery, voltage, supported_features, …). Ignored when
        # include_attributes (allowlist) is set.
        vol.Optional(ATTR_INCLUDE_ALL_ATTRIBUTES, default=True): cv.boolean,
        vol.Optional(ATTR_WRITE_FILE, default=True): cv.boolean,
        vol.Optional(ATTR_SCOPE, default="export"): cv.string,
        # Written-file format: json (full export) or csv (flat entity list).
        vol.Optional(ATTR_FORMAT, default=FORMAT_JSON): vol.In(FILE_FORMATS),
    }
)
