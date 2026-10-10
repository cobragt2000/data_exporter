# Changelog

## [2.4.0] - 2026-10-08

### Fixed
- Area-aware logic filtering now uses **containment** instead of intersection.
  A house-wide automation/script/scene that merely *touches* a selected room
  (e.g. a "smart plug offline" alert spanning six areas) is no longer pulled
  into a single-room export — only logic whose areas are fully within the
  selection is included. This stops cross-area references (e.g. grow-tent
  plugs) leaking into a Living Room export. Leave areas empty for everything.
- The card is now registered as a proper **Lovelace resource** (module), so it
  appears under Settings → Dashboards → Resources and loads before cards
  render — fixing the intermittent "custom element doesn't exist" error on
  reboot/refresh. Falls back to `extra_js_url` only in YAML-mode dashboards.
- The resource URL carries a `?v=` version query so browsers re-fetch the card
  after an upgrade instead of serving a stale cached copy; existing resources
  are updated in place rather than duplicated.
- The card guards `customElements.define` against double-registration.

## [2.3.0] - 2026-10-08

### Added
- Scripts and scenes are now included in the export (`include_scripts`,
  `include_scenes`, both default on), each with its full config and the
  entities/devices/areas it references — same treatment as automations.
- Card toggles for scripts and scenes; `script_count` / `scene_count` in the
  metadata and service response.

### Changed
- Automations, scripts, and scenes are now **area-aware**. When one or more
  areas are selected, only logic that references those areas (directly, or via
  a referenced entity/device that lives in them) is included. With no area
  filter (whole house / empty), all logic is returned — matching the entity
  list's scope.
- Each logic record now reports resolved `areas` (names) in addition to its
  referenced entities and devices.

## [2.2.0] - 2026-10-08

### Added
- Existing automations are now included in the export (`include_automations`,
  default on). Each automation record carries its full raw config
  (triggers/conditions/actions/mode), current state, last-triggered time, and
  the entities, devices, and areas it references — so a downstream LLM can see
  what's already set up alongside the available devices. Works for both
  UI-created and YAML automations.
- `include_automations` toggle on the card and the service, and an
  `automation_count` in the metadata and service response.

## [2.1.0] - 2026-10-08

### Added
- UI installation via a single-instance config flow (`config_flow.py`,
  `strings.json`, `translations/en.json`). The integration now appears under
  Settings → Devices & Services → Add Integration — no `configuration.yaml`
  entry required.

### Changed
- Setup moved from `async_setup` (YAML-triggered) to `async_setup_entry` /
  `async_unload_entry` (config entry). This fixes the card not registering and
  the integration not being UI-addable: the previous YAML-only setup never ran
  unless `data_exporter:` was added to `configuration.yaml`.
- Frontend card registration is now idempotent across config-entry reloads.

## [2.0.0] - 2026-10-08

Full rewrite to work against real Home Assistant and to be HACS-installable.

### Added
- Registry-based curation using the area/device/entity registries — no more
  placeholder data.
- Automatic filtering of diagnostic/config, hidden, and disabled entities,
  each toggleable per call.
- Manual overrides: `exclude_entities`, `exclude_attributes`, and an
  `include_attributes` allowlist.
- Service response support (`return_response: true` / `response_variable`)
  in addition to the JSON file export.
- `services.yaml` with area/entity/select selectors for a rich Developer
  Tools UI.
- Proper custom Lovelace card (`custom:data-exporter-card`) with live
  multi-select of areas and domains, auto-registered via the integration.
- HACS packaging: `hacs.json`, `info.md`, validation workflow (hassfest +
  HACS action), LICENSE.

### Changed
- Service now registered in `async_setup` with the correct `ServiceCall`
  handler signature (was `async_setup_entry` with a `(hass, data)` handler
  that never fired).
- File writes moved off the event loop into the executor.

### Removed
- Hardcoded long-lived access token in the card — the card now uses the
  authenticated `hass` connection.
- Placeholder/demo entity data.

## [1.0.0]

Initial prototype (placeholder data, non-functional service wiring).
