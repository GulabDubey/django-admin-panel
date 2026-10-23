(function () {
    "use strict";

    const presets = JSON.parse(document.getElementById("llm-presets").textContent);
    const existing = new Set(JSON.parse(document.getElementById("llm-existing-models").textContent));
    const config = JSON.parse(document.getElementById("llm-form-config").textContent);

    const presetSelect = document.getElementById("id_preset");
    const nameInput = document.getElementById("id_name");
    const apiTypeSelect = document.getElementById("id_api_type");
    const baseUrlInput = document.getElementById("id_base_url");
    const keyInput = document.getElementById("id_api_key");
    const selectedInput = document.getElementById("id_selected_models");
    const modelsFieldset = document.querySelector("fieldset.llm-available-models");
    if (!presetSelect || !keyInput || !selectedInput || !modelsFieldset) {
        return;
    }

    function el(tag, attrs, text) {
        const node = document.createElement(tag);
        Object.entries(attrs || {}).forEach(function ([key, value]) { node.setAttribute(key, value); });
        if (text) { node.textContent = text; }
        return node;
    }

    // --- "Get an API key" link under the key field -------------------------
    const keyLink = el("a", { class: "llm-key-link", target: "_blank", rel: "noopener noreferrer" });
    const keyHint = el("span", { class: "llm-key-hint" });
    const keyHelp = el("div");
    keyHelp.append(keyLink, keyHint);
    keyInput.closest("div").appendChild(keyHelp);

    // --- "Available models" picker -------------------------------------------
    const toolbar = el("div", { class: "llm-models-toolbar" });
    const loadButton = el("button", { type: "button", class: "button" }, "Load models");
    const filterInput = el("input", { type: "search", class: "llm-models-filter vTextField", placeholder: "Filter models…", hidden: "" });
    const selectAll = el("button", { type: "button", class: "button", hidden: "" }, "Select shown");
    const clearAll = el("button", { type: "button", class: "button", hidden: "" }, "Clear");
    const status = el("span", { class: "llm-models-status" },
        "Paste the API key, then load the models it can use.");
    toolbar.append(loadButton, filterInput, selectAll, clearAll, status);
    const list = el("div", { class: "llm-models-list" });
    modelsFieldset.append(toolbar, list);

    let previousPresetName = "";

    function applyPreset(initial) {
        const preset = presets[presetSelect.value] || presets.custom;

        if (!initial || !nameInput.value) {
            if (!nameInput.value || nameInput.value === previousPresetName) {
                nameInput.value = preset.name || "";
            }
        }
        previousPresetName = preset.name || "";

        if (!initial) {
            apiTypeSelect.value = preset.api_type;
            baseUrlInput.value = preset.base_url || "";
            list.innerHTML = "";
            setStatus("Paste the API key, then load the models it can use.");
            toggleListTools(false);
        }
        // Known providers fix the API type; only "custom" needs it chosen.
        apiTypeSelect.closest(".form-row").hidden = !preset.custom;

        if (preset.key_url) {
            keyLink.href = preset.key_url;
            keyLink.textContent = (presetSelect.value === "ollama" ? "Install Ollama" : "Get a " + (preset.name || "provider") + " API key") + " ↗";
            keyLink.hidden = false;
        } else {
            keyLink.hidden = true;
        }
        keyHint.textContent = preset.key_hint || "";
        keyInput.placeholder = preset.key_optional ? "optional" : (config.providerId ? "•••• stored — paste to replace" : "");
    }

    function setStatus(text, isError) {
        status.textContent = text;
        status.classList.toggle("error", Boolean(isError));
    }

    function toggleListTools(show) {
        [filterInput, selectAll, clearAll].forEach(function (node) { node.hidden = !show; });
    }

    function renderModels(models) {
        list.innerHTML = "";
        models.forEach(function (model) {
            const added = existing.has(model.id);
            const label = el("label", { class: added ? "added" : "", "data-search": (model.id + " " + model.name).toLowerCase() });
            const box = el("input", { type: "checkbox", value: model.id });
            if (added) {
                box.checked = true;
                box.disabled = true;
            }
            label.append(box, document.createTextNode(model.id));
            if (model.name && model.name !== model.id) {
                label.append(el("small", {}, model.name));
            }
            if (added) {
                label.append(el("small", {}, "added"));
            }
            list.appendChild(label);
        });
        toggleListTools(models.length > 0);
    }

    async function loadModels() {
        loadButton.disabled = true;
        setStatus("Loading models…");
        try {
            const response = await fetch(config.loadUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-CSRFToken": config.csrf },
                body: JSON.stringify({
                    api_type: apiTypeSelect.value,
                    base_url: baseUrlInput.value,
                    api_key: keyInput.value,
                    provider_id: config.providerId,
                }),
            });
            const data = await response.json().catch(function () { return {}; });
            if (!response.ok) {
                setStatus(data.error || "Could not load models.", true);
                return;
            }
            renderModels(data.models);
            const fresh = data.models.filter(function (m) { return !existing.has(m.id); }).length;
            setStatus(data.models.length + " models available" + (fresh ? " — tick the ones to use." : ", all already added."));
        } catch (error) {
            setStatus("Could not reach the server.", true);
        } finally {
            loadButton.disabled = false;
        }
    }

    filterInput.addEventListener("input", function () {
        const term = filterInput.value.trim().toLowerCase();
        list.querySelectorAll("label").forEach(function (label) {
            label.hidden = Boolean(term) && label.dataset.search.indexOf(term) === -1;
        });
    });
    selectAll.addEventListener("click", function () {
        list.querySelectorAll("label:not([hidden]) input:not(:disabled)").forEach(function (box) { box.checked = true; });
    });
    clearAll.addEventListener("click", function () {
        list.querySelectorAll("input:not(:disabled)").forEach(function (box) { box.checked = false; });
    });
    loadButton.addEventListener("click", loadModels);
    presetSelect.addEventListener("change", function () { applyPreset(false); });

    // Ticked models are submitted as a JSON list; the server creates them.
    presetSelect.form.addEventListener("submit", function () {
        const ids = Array.from(list.querySelectorAll("input:checked:not(:disabled)")).map(function (box) { return box.value; });
        selectedInput.value = JSON.stringify(ids);
    });

    applyPreset(true);
})();
