"""Entity Data Exporter integration.

A service integration that produces a *curated* list of Home Assistant
entities for feeding to an LLM (or any downstream tool). It reads HA's own
area / device / entity registries, automatically drops the noise HA already
knows about (diagnostic & config entities, plus hidden / disabled ones), and
lets you narrow by area and domain. Results are returned as a service
response AND optionally written to a JSON file in the config directory.

Set up from the UI (Settings -> Devices & Services -> Add Integration ->
Entity Data Exporter). It registers a single action:

    action: data_exporter.export_data
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse

from .const import CARD_VERSION, DOMAIN, SERVICE_EXPORT_DATA, SERVICE_SCHEMA
from .exporter import async_handle_export

_LOGGER = logging.getLogger(__name__)

# Path, inside this component, where the Lovelace card is served.
CARD_URL_BASE = f"/{DOMAIN}_static/data-exporter-card.js"
# Versioned URL so the browser re-fetches the card after an upgrade.
CARD_URL = f"{CARD_URL_BASE}?v={CARD_VERSION}"
# hass.data key used to make frontend registration idempotent across reloads.
_FRONTEND_DONE = f"{DOMAIN}_frontend_registered"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Entity Data Exporter from a config entry."""

    async def _export_service(call: ServiceCall) -> dict:
        """Handle a data_exporter.export_data service call."""
        return await async_handle_export(hass, call)

    # Idempotent: a reload re-enters here, so don't double-register.
    if not hass.services.has_service(DOMAIN, SERVICE_EXPORT_DATA):
        hass.services.async_register(
            DOMAIN,
            SERVICE_EXPORT_DATA,
            _export_service,
            schema=SERVICE_SCHEMA,
            # OPTIONAL = the caller may ask for the returned data, but the
            # service still works when called without `return_response: true`.
            supports_response=SupportsResponse.OPTIONAL,
        )

    # Serve and auto-load the bundled Lovelace card (once per HA run).
    await _async_register_frontend(hass)

    _LOGGER.info(
        "Entity Data Exporter set up; action %s.%s registered",
        DOMAIN,
        SERVICE_EXPORT_DATA,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if hass.services.has_service(DOMAIN, SERVICE_EXPORT_DATA):
        hass.services.async_remove(DOMAIN, SERVICE_EXPORT_DATA)
    # The static path / extra JS URL stays for the rest of the HA run; it is
    # harmless and removing it mid-run is not supported.
    return True


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the card and make the frontend load it reliably.

    Registers the static path, then tries to register the card as a proper
    Lovelace *resource* (so it appears under Settings -> Dashboards -> Resources
    and is loaded before cards render). Falls back to add_extra_js_url only when
    resource registration isn't possible (e.g. YAML-mode dashboards).
    """
    if hass.data.get(_FRONTEND_DONE):
        return

    www_dir = Path(__file__).parent / "www"

    try:
        # HA 2024.7+ API for registering static paths without blocking the
        # event loop.
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(f"/{DOMAIN}_static", str(www_dir), False)]
        )
    except (ImportError, AttributeError):
        # Fallback for older cores.
        hass.http.register_static_path(f"/{DOMAIN}_static", str(www_dir), False)
    except RuntimeError:
        # Path already registered this run — fine.
        pass

    registered = await _async_register_resource(hass)
    if not registered:
        # YAML-mode dashboards (or resources unavailable): inject as an extra
        # module so the card still loads.
        try:
            from homeassistant.components.frontend import add_extra_js_url

            add_extra_js_url(hass, CARD_URL)
            _LOGGER.info(
                "Registered card via extra_js_url (resource registration "
                "unavailable). In YAML-mode dashboards, add %s as a module "
                "resource if it doesn't appear.",
                CARD_URL,
            )
        except Exception as err:  # pragma: no cover - frontend not loaded
            _LOGGER.warning(
                "Could not auto-register the Lovelace card (%s). "
                "Add %s as a dashboard resource manually.",
                err,
                CARD_URL,
            )

    hass.data[_FRONTEND_DONE] = True


async def _async_register_resource(hass: HomeAssistant) -> bool:
    """Register (or update) the card as a storage-mode Lovelace resource.

    Returns True when the resource is in place, False when registration isn't
    possible (component not loaded, or YAML-mode resources which are read-only).
    """
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        return False

    # hass.data["lovelace"] is a dataclass on modern cores, a dict on older.
    resources = getattr(lovelace, "resources", None)
    if resources is None and isinstance(lovelace, dict):
        resources = lovelace.get("resources")
    if resources is None:
        return False

    # Only the storage-backed collection can be written to.
    if not hasattr(resources, "async_create_item"):
        return False

    try:
        # Ensure the collection is loaded before reading/writing.
        if hasattr(resources, "async_get_info"):
            await resources.async_get_info()
        elif not getattr(resources, "loaded", True):
            await resources.async_load()

        for item in resources.async_items():
            base = (item.get("url") or "").split("?")[0]
            if base == CARD_URL_BASE:
                # Already present — update the version query if it changed.
                if item.get("url") != CARD_URL:
                    await resources.async_update_item(
                        item["id"], {"res_type": "module", "url": CARD_URL}
                    )
                return True

        await resources.async_create_item(
            {"res_type": "module", "url": CARD_URL}
        )
        _LOGGER.info("Registered Lovelace resource %s", CARD_URL)
        return True
    except Exception as err:  # pragma: no cover - defensive
        _LOGGER.warning("Could not register Lovelace resource: %s", err)
        return False
