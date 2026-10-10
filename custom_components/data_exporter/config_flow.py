"""Config flow for Entity Data Exporter.

A minimal, single-instance config flow so the integration can be added from
Settings -> Devices & Services -> Add Integration. It takes no options; the
behaviour is all driven per-call through the export_data action.
"""
from __future__ import annotations

from typing import Any

from homeassistant import config_entries

from .const import DOMAIN


class DataExporterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Entity Data Exporter."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial (and only) step, confirming setup."""
        # Only one instance makes sense for this integration.
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title="Entity Data Exporter", data={}
            )

        return self.async_show_form(step_id="user")
