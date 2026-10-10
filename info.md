# Entity Data Exporter

Produces a **curated** list of your Home Assistant entities — filtered by area
and domain, with diagnostic/config/hidden/disabled entities and noisy
attributes (RSSI, battery, voltage…) removed — ready to hand to an LLM for
automation design.

- Reads HA's own area/device/entity registries (no placeholder data).
- Auto-drops the junk HA already tags, plus manual overrides.
- Returns a service response **and** writes a JSON file.
- Bundled custom Lovelace card with live multi-select — no token, no manual
  resource registration.

After install, restart HA, then add `type: custom:data-exporter-card` to a
dashboard or call the `data_exporter.export_data` action.
