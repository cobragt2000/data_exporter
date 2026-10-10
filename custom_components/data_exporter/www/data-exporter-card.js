/**
 * Entity Data Exporter — custom Lovelace card.
 *
 * A self-contained custom element (no build step, no external deps, no token).
 * It reads areas and domains live from the `hass` object, lets you multi-select
 * them, and calls the `data_exporter.export_data` action through the already
 * authenticated websocket connection.
 *
 * Add to a dashboard with:
 *   type: custom:data-exporter-card
 */
class DataExporterCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._built = false;
    this._config = {};
  }

  // Lovelace calls this with the card's YAML config.
  setConfig(config) {
    this._config = config || {};
  }

  getCardSize() {
    return 5;
  }

  // Lovelace sets this on first render and on every state change.
  set hass(hass) {
    const first = this._hass === null;
    this._hass = hass;
    if (!this._built) {
      this._build();
      this._built = true;
    }
    if (first) {
      this._populateAreas();
      this._populateDomains();
    }
  }

  get hass() {
    return this._hass;
  }

  _build() {
    const title = this._config.title || "Entity Data Exporter";
    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 16px; }
        .header { margin-bottom: 12px; }
        .header h2 { margin: 0; font-size: 1.3em; color: var(--primary-text-color); }
        .header p { margin: 4px 0 0; color: var(--secondary-text-color); font-size: 0.9em; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        @media (max-width: 500px) { .grid { grid-template-columns: 1fr; } }
        .field { display: flex; flex-direction: column; }
        label { font-weight: 500; margin-bottom: 6px; color: var(--secondary-text-color); font-size: 0.9em; }
        select[multiple] {
          width: 100%; min-height: 150px; padding: 6px;
          border-radius: 6px;
          border: 1px solid var(--divider-color, #c7c7c7);
          background: var(--card-background-color, var(--ha-card-background));
          color: var(--primary-text-color);
          font-size: 0.95em;
        }
        select[multiple] option { padding: 3px 6px; }
        .hint { color: var(--secondary-text-color); font-size: 0.78em; margin-top: 4px; }
        .toggles { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 14px; }
        .toggle { display: flex; align-items: center; gap: 6px; color: var(--primary-text-color); font-size: 0.9em; }
        .scope-row { margin-top: 14px; display: flex; flex-direction: column; }
        .scope-row input[type=text] {
          padding: 8px; border-radius: 6px;
          border: 1px solid var(--divider-color, #c7c7c7);
          background: var(--card-background-color, var(--ha-card-background));
          color: var(--primary-text-color);
        }
        button.run {
          margin-top: 18px; width: 100%; padding: 12px;
          background: var(--primary-color); color: var(--text-primary-color, #fff);
          border: none; border-radius: 8px; font-size: 1.05em; font-weight: 600;
          cursor: pointer;
        }
        button.run:disabled { opacity: 0.6; cursor: default; }
        .status { margin-top: 14px; padding: 10px; border-radius: 6px; font-size: 0.9em; word-break: break-word; }
        .status.ok { background: rgba(76,175,80,0.15); color: var(--success-color, #2e7d32); }
        .status.err { background: rgba(244,67,54,0.15); color: var(--error-color, #c62828); }
        .status.busy { background: var(--secondary-background-color); color: var(--secondary-text-color); }
      </style>
      <ha-card>
        <div class="header">
          <h2>${title}</h2>
          <p>Select areas and domains, then export a curated entity list.</p>
        </div>
        <div class="grid">
          <div class="field">
            <label for="areas">Areas <span class="hint">(none = all)</span></label>
            <select id="areas" multiple></select>
          </div>
          <div class="field">
            <label for="domains">Domains <span class="hint">(none = all)</span></label>
            <select id="domains" multiple></select>
          </div>
        </div>
        <div class="toggles">
          <label class="toggle"><input type="checkbox" id="diag"> Include diagnostic/config</label>
          <label class="toggle"><input type="checkbox" id="hidden"> Include hidden</label>
          <label class="toggle"><input type="checkbox" id="disabled"> Include disabled</label>
          <label class="toggle"><input type="checkbox" id="automations" checked> Include automations</label>
          <label class="toggle"><input type="checkbox" id="scripts" checked> Include scripts</label>
          <label class="toggle"><input type="checkbox" id="scenes" checked> Include scenes</label>
          <label class="toggle"><input type="checkbox" id="writefile" checked> Write JSON file</label>
        </div>
        <div class="scope-row">
          <label for="scope">Scope label</label>
          <input type="text" id="scope" value="export" />
        </div>
        <button class="run" id="run">Run Export</button>
        <div class="status" id="status" style="display:none;"></div>
      </ha-card>
    `;

    this.shadowRoot.getElementById("run").addEventListener("click", () =>
      this._runExport()
    );
  }

  _populateAreas() {
    const sel = this.shadowRoot.getElementById("areas");
    if (!sel || !this._hass) return;
    const areas = Object.values(this._hass.areas || {});
    areas.sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    sel.innerHTML = areas
      .map((a) => `<option value="${a.area_id}">${a.name}</option>`)
      .join("");
  }

  _populateDomains() {
    const sel = this.shadowRoot.getElementById("domains");
    if (!sel || !this._hass) return;
    const domains = new Set();
    Object.keys(this._hass.states || {}).forEach((eid) =>
      domains.add(eid.split(".")[0])
    );
    const sorted = [...domains].sort();
    sel.innerHTML = sorted
      .map((d) => `<option value="${d}">${d}</option>`)
      .join("");
  }

  _selectedValues(id) {
    const sel = this.shadowRoot.getElementById(id);
    if (!sel) return [];
    return [...sel.selectedOptions].map((o) => o.value);
  }

  _setStatus(kind, html) {
    const s = this.shadowRoot.getElementById("status");
    s.style.display = "block";
    s.className = `status ${kind}`;
    s.innerHTML = html;
  }

  async _runExport() {
    if (!this._hass) return;
    const btn = this.shadowRoot.getElementById("run");
    btn.disabled = true;
    this._setStatus("busy", "Running export…");

    const data = {
      areas: this._selectedValues("areas"),
      domains: this._selectedValues("domains"),
      include_diagnostic: this.shadowRoot.getElementById("diag").checked,
      include_hidden: this.shadowRoot.getElementById("hidden").checked,
      include_disabled: this.shadowRoot.getElementById("disabled").checked,
      include_automations: this.shadowRoot.getElementById("automations").checked,
      include_scripts: this.shadowRoot.getElementById("scripts").checked,
      include_scenes: this.shadowRoot.getElementById("scenes").checked,
      write_file: this.shadowRoot.getElementById("writefile").checked,
      scope: this.shadowRoot.getElementById("scope").value || "export",
    };
    // Drop empty lists so the service treats them as "all".
    if (data.areas.length === 0) delete data.areas;
    if (data.domains.length === 0) delete data.domains;

    try {
      // 6th arg = return_response. Works on modern HA frontends.
      const result = await this._hass.callService(
        "data_exporter",
        "export_data",
        data,
        undefined,
        false,
        true
      );
      const resp = (result && result.response) || {};
      const count = resp.entity_count != null ? resp.entity_count : "?";
      const path = resp.file_path;
      const extras = [];
      if (resp.automation_count != null) extras.push(`${resp.automation_count} automations`);
      if (resp.script_count != null) extras.push(`${resp.script_count} scripts`);
      if (resp.scene_count != null) extras.push(`${resp.scene_count} scenes`);
      let msg = `✅ Exported ${count} entities`;
      if (extras.length) msg += ` + ${extras.join(", ")}`;
      msg += ".";
      if (path) msg += `<br>Saved to: <code>${path}</code>`;
      else if (data.write_file) msg += ` (file write skipped/failed — check logs)`;
      this._setStatus("ok", msg);
    } catch (err) {
      this._setStatus(
        "err",
        `❌ Export failed: ${err && err.message ? err.message : err}`
      );
    } finally {
      btn.disabled = false;
    }
  }
}

// Guard against double-registration (resource + extra_js_url, or a reload),
// which would otherwise throw "has already been used with this registry".
if (!customElements.get("data-exporter-card")) {
  customElements.define("data-exporter-card", DataExporterCard);

  // Make the card show up in the dashboard "Add card" picker.
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "data-exporter-card",
    name: "Entity Data Exporter",
    description:
      "Export a curated list of entities filtered by area and domain.",
  });
}

console.info("%c DATA-EXPORTER-CARD %c loaded ", "color:#fff;background:#03a9f4;border-radius:3px 0 0 3px;padding:2px 4px;", "color:#03a9f4;background:#fff;border-radius:0 3px 3px 0;padding:2px 4px;");
