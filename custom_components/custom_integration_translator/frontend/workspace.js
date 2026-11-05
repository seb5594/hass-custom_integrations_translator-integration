const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);

class TranslatorWorkspace extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this.hiddenComplete = true;
    this.items = [];
    this.terms = "";
    this.selected = new Set();
    this.root = this.shadowRoot;
    this.root.addEventListener("click", e => this.click(e));
    this.root.addEventListener("change", e => this.change(e));
    this.root.addEventListener("input", e => {
      if (e.target.id === "terms") this.terms = e.target.value;
    });
  }

  set hass(value) {
    this.ha = value;
    if (this.isConnected) this.start();
  }
  connectedCallback() { this.start(); }
  start() {
    if (!this.ha || this.started) return;
    this.started = true;
    this.run(async () => {
      this.settings = await this.call("settings");
      this.terms = this.settings.terms || "";
      const query = this.popup ? new URLSearchParams() : new URLSearchParams(location.search);
      const choices = this.languages();
      this.lang = query.get("language") || this.settings.language;
      if (!choices.includes(this.lang)) this.lang = "";
      if (this.lang) {
        await this.list();
        if (this.items.some(i => i.domain === query.get("domain") && !i.error)) {
          await this.detail(query.get("domain"));
        }
      }
    });
  }
  languages() { return [...new Set([...this.settings.languages, ...this.settings.recoverable])].sort(); }
  t(de, en) { return (this.ha?.language || "en").startsWith("de") ? de : en; }
  label(code) {
    try { return new Intl.DisplayNames([this.ha.language], {type:"language"}).of(code) + ` (${code})`; }
    catch { return code; }
  }
  call(action, data = {}) {
    return this.ha.callWS({type:"custom_integration_translator/workspace", action, ...data});
  }
  async run(work) {
    if (this.busy) return;
    this.busy = true;
    this.message = "";
    this.error = "";
    this.render();
    try { await work(); }
    catch (err) { this.error = err.message || String(err); }
    finally { this.busy = false; this.render(); }
  }
  async list() {
    this.item = null;
    this.items = await this.call("list", {language:this.lang});
  }
  async detail(domain) {
    this.item = await this.call("detail", {language:this.lang, domain});
    this.select("missing");
  }
  select(mode) {
    this.selected = new Set(this.item.rows.flatMap((r, index) =>
      mode === "all" || (mode === "missing" && r.target === null) ? [index] : []));
  }
  change({target}) {
    if (target.id === "language") {
      this.lang = target.value;
      this.run(() => this.list());
    } else if (target.id === "hide") {
      this.hiddenComplete = target.checked;
      this.render();
    } else if (target.dataset.row !== undefined) {
      const index = Number(target.dataset.row);
      if (target.checked) this.selected.add(index); else this.selected.delete(index);
      this.updateSubmit();
    }
  }
  updateSubmit() {
    const submit = this.root.querySelector("#translate");
    if (!submit) return;
    submit.disabled = this.busy || !this.selected.size || this.item.conflict ||
      !this.settings.languages.includes(this.lang);
    submit.textContent = this.t("Auswahl übersetzen", "Translate selection") + ` (${this.selected.size})`;
  }
  click(event) {
    const button = event.target.closest("button");
    if (!button || button.disabled) return;
    const id = button.id;
    if (id === "close") return this.dispatchEvent(new Event("cit-close", {bubbles:true, composed:true}));
    if (id === "menu") return this.dispatchEvent(new CustomEvent("hass-toggle-menu", {bubbles:true, composed:true}));
    if (id === "retry") { this.started = false; return this.start(); }
    if (id === "back") return this.run(() => this.list());
    if (button.dataset.domain) return this.run(() => this.detail(button.dataset.domain));
    if (button.dataset.select) { this.select(button.dataset.select); this.render(); return; }
    if (!this.item) return;
    const data = {domain:this.item.domain, language:this.lang};
    if (id === "translate") {
      const paths = [...this.selected].map(index => this.item.rows[index].path);
      return this.run(async () => {
        await this.call("translate", {...data, paths, revision:this.item.revision, terms:this.terms.split("\n")});
        await this.detail(data.domain);
        this.message = this.t(`${paths.length} Phrasen gespeichert.`, `Saved ${paths.length} phrases.`) + " " +
          this.t("Nach einem Neustart von Home Assistant und Neuladen des Browsers werden die Änderungen sichtbar.",
                 "Restart Home Assistant and refresh your browser to see the changes.");
      });
    }
    if (id === "restore") {
      const confirm = this.item.original
        ? this.item.conflict
          ? this.t("Aktuelle Datei zusätzlich als .bak sichern und das ursprüngliche Original wiederherstellen?", "Save the current file as an additional .bak and restore the initial original?")
          : this.t("Die gesicherte Originaldatei wiederherstellen?", "Restore the saved original file?")
        : this.t("Die von diesem Werkzeug erzeugte Sprachdatei löschen?", "Delete the language file created by this tool?");
      if (window.confirm(confirm)) this.run(async () => {
        await this.call("restore", {...data, revision:this.item.revision});
        await this.detail(data.domain);
        this.message = this.t("Änderungen rückgängig gemacht.", "Changes undone.");
      });
    }
    if (id === "download") this.run(async () => {
      const raw = atob(await this.call("original", data));
      const url = URL.createObjectURL(new Blob([Uint8Array.from(raw, c => c.charCodeAt(0))], {type:"application/json"}));
      const a = document.createElement("a");
      a.href = url; a.download = this.lang + ".json"; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    });
  }
  listView() {
    const t = this.t.bind(this);
    const items = this.items.filter(i => !this.hiddenComplete || i.missing || i.conflict || i.error || !i.exists);
    return `<h2>${t("1 · Integration auswählen","1 · Choose an integration")}</h2>
      <label><input id="hide" type="checkbox" ${this.hiddenComplete ? "checked" : ""}> ${t("Verstecke übersetzte Integrationen","Hide translated integrations")}</label>
      <ul>${items.map(i => `<li><button class="item" data-domain="${escapeHtml(i.domain)}" ${i.error ? "disabled" : ""}>
        <span>${escapeHtml(i.name)}<small>${escapeHtml(i.domain)}</small></span>
        <span>${escapeHtml(i.error || (i.conflict ? t("Datei geändert","File changed") :
          i.missing ? t(`${i.missing} fehlen`,`${i.missing} missing`) :
          i.count || i.exists ? t("Vollständig","Complete") : t("Keine Quellphrasen","No source phrases")))}</span></button></li>`).join("")}</ul>
      ${items.length ? "" : t("Keine Integrationen für diesen Filter.","No integrations match this filter.")}`;
  }
  editor() {
    const t = this.t.bind(this), item = this.item;
    return `<button id="back">‹ ${t("Integrationen","Integrations")}</button>
      <h2>${escapeHtml(item.name)}</h2>
      <p>${t("2 · Phrasen auswählen. Fehlende Texte sind bereits markiert. Vorhandene Werte werden nur bei Auswahl ersetzt.",
            "2 · Choose phrases. Missing texts are selected. Existing values are replaced only when selected.")}</p>
      ${item.conflict ? `<p role="alert">${t("Die Datei wurde außerhalb des Translators geändert. Automatische Änderungen sind gesperrt.","The file changed outside the translator. Automatic changes are blocked.")}</p>` : ""}
      <div class="tools"><button data-select="missing">${t("Nur fehlende","Missing only")}</button>
      <button data-select="all">${t("Alle auswählen","Select all")}</button>
      <button data-select="none">${t("Auswahl aufheben","Clear selection")}</button></div>
      ${item.rows.map((r,index) => `<label class="phrase"><input type="checkbox" data-row="${index}" ${this.selected.has(index)?"checked":""}>
        <span><small>${escapeHtml(item.source_language)} · ${escapeHtml(r.path.join(" › "))}</small>${escapeHtml(r.source)}</span>
        <span><small>${escapeHtml(this.lang)} · ${r.target === null ? t("fehlt","missing") : r.generated ? "DeepL" : t("Vorhandene Fassung","Existing translation")}</small>${r.target === null ? "—" : escapeHtml(r.target)}</span></label>`).join("") ||
          `<p>${t("Keine Phrasen in einer anderen Quelldatei gefunden.","No phrases found in a separate source file.")}</p>`}
      <label class="terms">${t("Geschützte Wörter, eines pro Zeile","Protected words, one per line")}
        <textarea id="terms" rows="3" placeholder="Home Assistant&#10;DeepL">${escapeHtml(this.terms)}</textarea></label>
      <p>${t("Schreibweise beachten. Nur die ausgewählten Quelltexte werden an DeepL übergeben.",
            "Match the spelling exactly. Only selected source texts are submitted to DeepL.")}</p>
      <button class="primary" id="translate"></button>
      ${item.managed ? `<hr><button id="restore" ${item.conflict && !item.original?"disabled":""}>${item.original ? t("Original wiederherstellen","Restore original") : t("Erzeugte Datei löschen","Delete generated file")}</button>` : ""}
      ${item.initial_available ? `<button id="download">${t("Erste Entwicklerfassung herunterladen","Download initial developer version")}</button>` : ""}`;
  }
  render() {
    const t = this.t.bind(this);
    const options = this.settings ? this.languages().map(code =>
      `<option value="${escapeHtml(code)}" ${this.lang===code?"selected":""}>${escapeHtml(this.label(code))}</option>`).join("") : "";
    this.root.innerHTML = `<link rel="stylesheet" href="/custom_integration_translator_assets/workspace.css">
      <article><header>${this.popup ? "" : `<button id="menu" aria-label="${t("Menü","Menu")}"><ha-icon icon="mdi:menu"></ha-icon></button>`}
      <ha-icon icon="mdi:translate"></ha-icon><h1>Custom Integration Translator</h1>
      ${this.popup ? `<button id="close" aria-label="${t("Schließen","Close")}">✕</button>` : ""}</header>
      <main>${this.error ? `<p role="alert">${escapeHtml(this.error)} <button id="retry">${t("Neu laden","Reload")}</button></p>` : ""}
      ${this.settings?.error ? `<p role="alert">${escapeHtml(this.settings.error)}</p>` : ""}
      ${this.busy ? `<p role="status">${t("Wird verarbeitet …","Working …")}</p>` : ""}
      ${this.message ? `<p role="status">${escapeHtml(this.message)}</p>` : ""}
      <fieldset ${this.busy?"disabled":""}>${this.settings ? `<label>${t("Zielsprache","Target language")}
        <select id="language">${this.lang ? "" : `<option disabled selected>${t("Sprache wählen","Choose language")}</option>`}${options}</select></label>
        ${!this.lang ? `<p>${t("Die voreingestellte Sprache ist bei DeepL nicht verfügbar. Bitte eine angebotene Sprache wählen.","The default language is unavailable from DeepL. Choose an available language.")}</p>` :
          this.item ? this.editor() : this.listView()}` : ""}</fieldset></main>
      <footer><a href="https://github.com/seb5594" target="_blank" rel="noopener noreferrer">More Developer's Home Assistant Content</a>
      <a href="https://paypal.me/seb5594" target="_blank" rel="noopener noreferrer">Support work</a><p>Made with 💖 in 🇩🇪</p></footer></article>`;
    this.updateSubmit();
  }
}
if (!customElements.get("cit-workspace")) customElements.define("cit-workspace", TranslatorWorkspace);
