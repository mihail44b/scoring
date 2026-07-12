let allPresets = {};
let currentPresetName = "";
let currentPresetData = null;
let currentTab = "general";

async function loadPresets() {
    try {
        const response = await fetch('/api/settings/configs');
        allPresets = await response.json();
        
        const selector = document.getElementById("preset-selector");
        selector.innerHTML = "";
        
        const filenames = Object.keys(allPresets).sort();
        if (filenames.length === 0) {
            selector.innerHTML = "<option>Нет доступных пресетов</option>";
            return;
        }

        filenames.forEach(file => {
            const opt = document.createElement("option");
            opt.value = file;
            opt.textContent = file;
            selector.appendChild(opt);
        });

        changePreset(filenames[0]);
    } catch (e) {
        console.error("Ошибка загрузки пресетов:", e);
    }
}

function changePreset(name) {
    const selector = document.getElementById("preset-selector");
    if (!name) name = selector.value;
    else selector.value = name;

    currentPresetName = name;
    // Работаем с копией
    currentPresetData = JSON.parse(JSON.stringify(allPresets[name]));
    
    renderSidebar();
    selectTab("general");
}

function renderSidebar() {
    const sidebar = document.getElementById("tab-list");
    sidebar.innerHTML = "";

    // Вкладка Общие настройки
    sidebar.appendChild(createTabEl("general", "⚙️ Общие настройки"));

    // Вкладки Категорий
    if (currentPresetData.categories && Array.isArray(currentPresetData.categories)) {
        currentPresetData.categories.forEach((cat, index) => {
            sidebar.appendChild(createTabEl(`cat_${index}`, `📁 ${cat.name || cat.id}`));
        });
    }

    // Вкладка Raw JSON
    sidebar.appendChild(createTabEl("raw", "💻 Raw JSON"));
}

function createTabEl(id, title) {
    const div = document.createElement("div");
    div.className = "tab-item";
    div.id = `tab-${id}`;
    div.textContent = title;
    div.onclick = () => selectTab(id, title);
    return div;
}

function selectTab(id, title = null) {
    currentTab = id;
    document.querySelectorAll(".tab-item").forEach(el => el.classList.remove("active"));
    const activeEl = document.getElementById(`tab-${id}`);
    if (activeEl) {
        activeEl.classList.add("active");
        if (!title) title = activeEl.textContent;
    }

    document.getElementById("current-tab-title").textContent = title;

    const formContainer = document.getElementById("form-container");
    const jsonEditor = document.getElementById("json-editor");

    formContainer.innerHTML = "";
    
    if (id === "raw") {
        formContainer.style.display = "none";
        jsonEditor.style.display = "block";
        document.getElementById("raw-json-textarea").value = JSON.stringify(currentPresetData, null, 4);
    } else {
        formContainer.style.display = "block";
        jsonEditor.style.display = "none";

        if (id === "general") {
            renderGeneralSettings(formContainer);
        } else if (id.startsWith("cat_")) {
            const idx = parseInt(id.split("_")[1]);
            renderCategorySettings(formContainer, currentPresetData.categories[idx], idx);
        }
    }
}

// ─── Утилита распределения весов ────────────────────────────────────────────

function renderWeightDistribution(container, titleText, items, labelExtractor) {
    const section = createSection(titleText);
    container.appendChild(section);

    const wrapper = document.createElement("div");
    wrapper.style.background = "var(--glass-bg)";
    wrapper.style.border = "1px solid var(--border-color)";
    wrapper.style.borderRadius = "12px";
    wrapper.style.padding = "20px";
    wrapper.style.marginBottom = "24px";

    const inputsContainer = document.createElement("div");
    wrapper.appendChild(inputsContainer);

    const sumEl = document.createElement("div");
    sumEl.style.marginTop = "16px";
    sumEl.style.paddingTop = "16px";
    sumEl.style.borderTop = "1px dashed var(--border-color)";
    sumEl.style.fontWeight = "600";
    sumEl.style.fontSize = "15px";
    sumEl.style.display = "flex";
    sumEl.style.justifyContent = "space-between";
    wrapper.appendChild(sumEl);

    function updateSum() {
        let sum = 0;
        items.forEach(item => sum += (item.weight || 0));
        sum = Math.round(sum * 1000) / 1000; // Устранение погрешностей
        
        if (sum === 1) {
            sumEl.innerHTML = `<span>Сумма весов:</span> <span style="color: #10b981;">1.00 ✓</span>`;
        } else {
            sumEl.innerHTML = `<span>Сумма весов:</span> <span style="color: #ef4444;">${sum} (Должно быть 1.0) ⚠️</span>`;
        }
    }

    items.forEach(item => {
        const label = labelExtractor(item);
        const row = createInputRow(label, item.weight, (val) => {
            item.weight = Number(val);
            updateSum();
        }, "number");
        inputsContainer.appendChild(row);
    });

    updateSum();
    container.appendChild(wrapper);
}

// ─── Рендер Общих Настроек ──────────────────────────────────────────────────

function renderGeneralSettings(container) {
    // Веса категорий
    if (currentPresetData.categories) {
        renderWeightDistribution(
            container, 
            "Веса категорий (Сумма = 1.0)", 
            currentPresetData.categories, 
            (cat) => cat.name || cat.id
        );
    }

    // ID Columns
    container.appendChild(createSection("Колонки-идентификаторы (переносятся в итоговый отчет)"));
    const idHint = document.createElement("div");
    idHint.style.fontSize = "13px";
    idHint.style.color = "var(--text-secondary)";
    idHint.style.marginBottom = "12px";
    idHint.textContent = "Эти колонки не участвуют в расчетах, но они обязательны для идентификации компаний в итоговом файле.";
    container.appendChild(idHint);

    container.appendChild(createInputRow("Колонки (через запятую)", (currentPresetData.id_columns || []).join(", "), (val) => {
        currentPresetData.id_columns = val.split(",").map(s => s.trim()).filter(s => s);
    }));



    // Segments
    container.appendChild(createSection("Сегментация"));
    for (const [key, seg] of Object.entries(currentPresetData.segments || {})) {
        const row = document.createElement("div");
        row.className = "form-row";
        
        const label = document.createElement("div");
        label.className = "form-label";
        label.textContent = `Сегмент: ${key}`;
        
        const labelInput = document.createElement("input");
        labelInput.className = "form-input";
        labelInput.value = seg.label;
        labelInput.placeholder = "Название";
        labelInput.onchange = (e) => seg.label = e.target.value;

        const scoreInput = document.createElement("input");
        scoreInput.className = "form-input";
        scoreInput.type = "number";
        scoreInput.value = seg.min_score;
        scoreInput.placeholder = "Мин. балл";
        scoreInput.style.maxWidth = "100px";
        scoreInput.onchange = (e) => seg.min_score = Number(e.target.value);

        row.appendChild(label);
        row.appendChild(labelInput);
        row.appendChild(scoreInput);
        container.appendChild(row);
    }

    // Enrichment
    container.appendChild(createSection("Веса приоритета обогащения"));
    const ew = currentPresetData.enrichment_weights || {};
    container.appendChild(createInputRow("Вес скоринга", ew.score_weight, (val) => ew.score_weight = Number(val), "number"));
    container.appendChild(createInputRow("Вес энтропии", ew.entropy_weight, (val) => ew.entropy_weight = Number(val), "number"));
}

// ─── Рендер Категории ───────────────────────────────────────────────────────

function renderCategorySettings(container, category, catIndex) {
    // Основные настройки категории
    container.appendChild(createInputRow("Slug", category.id, (val) => category.id = val));
    container.appendChild(createInputRow("Название", category.name, (val) => category.name = val));

    if (category.id === "A" || category.name === "Фин. здоровье") {
        container.appendChild(createSection("Региональные коэффициенты"));
        const rc = currentPresetData.regional_coefficients || { keywords: [], rules: {} };
        if (!currentPresetData.regional_coefficients) currentPresetData.regional_coefficients = rc;

        container.appendChild(createInputRow("Ключевые слова адреса", (rc.keywords || []).join(", "), (val) => {
            rc.keywords = val.split(",").map(s => s.trim()).filter(s => s);
        }));
        
        const regRulesContainer = document.createElement("div");
        regRulesContainer.style.marginLeft = "16px";
        regRulesContainer.style.marginBottom = "16px";
        
        const regRulesTitle = document.createElement("div");
        regRulesTitle.textContent = "Правила (Регион -> Множитель порога):";
        regRulesTitle.style.fontSize = "13px";
        regRulesTitle.style.fontWeight = "600";
        regRulesTitle.style.marginBottom = "8px";
        regRulesContainer.appendChild(regRulesTitle);
        
        renderDictionaryEditor(regRulesContainer, rc.rules, (newRules) => {
            rc.rules = newRules;
        });
        container.appendChild(regRulesContainer);
    }

    // Веса признаков в самом верху
    if (category.features) {
        renderWeightDistribution(
            container, 
            "Веса признаков внутри категории (Сумма = 1.0)", 
            category.features, 
            (feat) => feat.name || feat.id
        );
    }

    container.appendChild(createSection(`Параметры признаков (${category.features ? category.features.length : 0})`));

    (category.features || []).forEach((feat, fIndex) => {
        const card = document.createElement("div");
        card.className = "feature-card";

        const header = document.createElement("div");
        header.className = "feature-header";
        header.textContent = `Признак: ${feat.name || feat.id}`;
        card.appendChild(header);

        card.appendChild(createInputRow("Название", feat.name || "", (val) => {
            feat.name = val;
            header.textContent = `Признак: ${val}`;
        }));
        card.appendChild(createInputRow("Slug", feat.id, (val) => feat.id = val));
        
        // ВЕС УБРАН ИЗ КАРТОЧКИ, так как он редактируется в верхнем блоке

        if (feat.scoring_method && feat.scoring_method.params) {
            const p = feat.scoring_method.params;
            if (p.threshold !== undefined) {
                card.appendChild(createInputRow("Порог", p.threshold, (val) => p.threshold = Number(val), "number"));
            }
            if (p.scale !== undefined) {
                card.appendChild(createInputRow("Шкала", p.scale, (val) => p.scale = Number(val), "number"));
            }
            if (p.mapping !== undefined) {
                const dictWrapper = document.createElement("div");
                dictWrapper.style.marginTop = "16px";
                const dictTitle = document.createElement("div");
                dictTitle.textContent = "Справочник баллов (Значение -> Балл):";
                dictTitle.style.fontSize = "13px";
                dictTitle.style.fontWeight = "600";
                dictTitle.style.marginBottom = "8px";
                dictWrapper.appendChild(dictTitle);
                
                renderDictionaryEditor(dictWrapper, p.mapping, (newMapping) => {
                    p.mapping = newMapping;
                });
                card.appendChild(dictWrapper);
            }
        }

        container.appendChild(card);
    });
}

// ─── Утилиты UI ─────────────────────────────────────────────────────────────

function createSection(titleText) {
    const el = document.createElement("div");
    el.className = "section-title";
    el.textContent = titleText;
    return el;
}

function createInputRow(labelText, value, onChangeCallback, type="text") {
    const row = document.createElement("div");
    row.className = "form-row";
    
    const label = document.createElement("div");
    label.className = "form-label";
    label.textContent = labelText;
    
    const input = document.createElement("input");
    input.className = "form-input";
    if (type === "number") {
        input.type = "number";
        input.step = "any";
    } else {
        input.type = "text";
    }
    input.value = value !== undefined && value !== null ? value : "";
    
    input.onchange = (e) => {
        onChangeCallback(e.target.value);
    };

    row.appendChild(label);
    row.appendChild(input);
    return row;
}

function renderDictionaryEditor(container, mappingData, onChangeCallback) {
    const table = document.createElement("div");
    table.style.display = "flex";
    table.style.flexDirection = "column";
    table.style.gap = "8px";

    function renderRows() {
        table.innerHTML = "";
        
        // Add Button
        const addRow = document.createElement("div");
        const addBtn = document.createElement("button");
        addBtn.textContent = "+ Добавить правило";
        addBtn.style.padding = "4px 12px";
        addBtn.style.fontSize = "12px";
        addBtn.style.background = "var(--primary-gradient)";
        addBtn.style.color = "white";
        addBtn.style.border = "none";
        addBtn.style.borderRadius = "4px";
        addBtn.style.cursor = "pointer";
        addBtn.onclick = () => {
            mappingData["НОВОЕ_ЗНАЧЕНИЕ"] = 0;
            onChangeCallback(mappingData);
            renderRows();
        };
        addRow.appendChild(addBtn);
        table.appendChild(addRow);

        for (const [key, val] of Object.entries(mappingData)) {
            const row = document.createElement("div");
            row.style.display = "flex";
            row.style.gap = "8px";

            const keyInput = document.createElement("input");
            keyInput.className = "form-input";
            keyInput.value = key;
            keyInput.style.maxWidth = "200px";
            keyInput.onchange = (e) => {
                const newKey = e.target.value;
                if (newKey !== key) {
                    mappingData[newKey] = mappingData[key];
                    delete mappingData[key];
                    onChangeCallback(mappingData);
                    renderRows();
                }
            };

            const valInput = document.createElement("input");
            valInput.className = "form-input";
            valInput.type = "number";
            valInput.step = "any";
            valInput.value = val;
            valInput.style.maxWidth = "100px";
            valInput.onchange = (e) => {
                mappingData[key] = Number(e.target.value);
                onChangeCallback(mappingData);
            };

            const delBtn = document.createElement("button");
            delBtn.textContent = "✕";
            delBtn.style.background = "none";
            delBtn.style.border = "none";
            delBtn.style.color = "#ef4444";
            delBtn.style.cursor = "pointer";
            delBtn.onclick = () => {
                delete mappingData[key];
                onChangeCallback(mappingData);
                renderRows();
            };

            row.appendChild(keyInput);
            row.appendChild(valInput);
            row.appendChild(delBtn);
            table.appendChild(row);
        }
    }
    
    renderRows();
    container.appendChild(table);
}

// ─── Сохранение ─────────────────────────────────────────────────────────────

function applyRawJson() {
    try {
        const text = document.getElementById("raw-json-textarea").value;
        const parsed = JSON.parse(text);
        currentPresetData = parsed;
        alert("JSON успешно применён в памяти. Нажмите 'Сохранить пресет' чтобы записать на диск.");
        renderSidebar();
    } catch(e) {
        alert("Ошибка в синтаксисе JSON: " + e.message);
    }
}

async function saveCurrentPreset() {
    if (!currentPresetName) return;

    // Валидация весов
    let isValid = true;
    let errors = [];

    // 1. Веса категорий
    let catSum = 0;
    (currentPresetData.categories || []).forEach(c => catSum += (c.weight || 0));
    catSum = Math.round(catSum * 1000) / 1000;
    if (catSum !== 1) {
        isValid = false;
        errors.push("Сумма весов категорий должна быть равна 1.0.");
    }

    // 2. Веса признаков в каждой категории
    (currentPresetData.categories || []).forEach(c => {
        let featSum = 0;
        (c.features || []).forEach(f => featSum += (f.weight || 0));
        featSum = Math.round(featSum * 1000) / 1000;
        if (featSum !== 1) {
            isValid = false;
            errors.push(`В категории "${c.name || c.id}" сумма весов признаков равна ${featSum} (должна быть 1.0).`);
        }
    });

    if (!isValid && currentTab !== "raw") {
        alert("ОШИБКА ВЕСОВ:\n\n" + errors.join("\n") + "\n\nИсправьте значения перед сохранением.");
        return; // Блокируем сохранение если веса не равны 1
    }

    if (currentTab === "raw") {
        try {
            currentPresetData = JSON.parse(document.getElementById("raw-json-textarea").value);
        } catch(e) {
            alert("Ошибка в синтаксисе JSON. Исправьте перед сохранением.");
            return;
        }
    }

    const payload = {};
    payload[currentPresetName] = currentPresetData;
    
    const statusEl = document.getElementById("save-status");
    statusEl.textContent = "Сохранение...";
    statusEl.style.display = "inline";
    
    try {
        const res = await fetch("/api/settings/configs", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        
        if (res.ok) {
            statusEl.textContent = "✅ Сохранено";
            allPresets[currentPresetName] = JSON.parse(JSON.stringify(currentPresetData));
        } else {
            statusEl.textContent = "❌ Ошибка сервера";
            statusEl.style.color = "#ef4444";
        }
    } catch (e) {
        statusEl.textContent = "❌ Ошибка сети";
        statusEl.style.color = "#ef4444";
    }
    
    setTimeout(() => { 
        statusEl.style.display = "none"; 
        statusEl.style.color = "#10b981"; 
    }, 3000);
}

// ─── Тема ───────────────────────────────────────────────────────────────────

function toggleTheme() {
    const root = document.documentElement;
    const currentTheme = root.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
}

document.addEventListener("DOMContentLoaded", () => {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
        document.documentElement.setAttribute('data-theme', savedTheme);
    } else {
        document.documentElement.setAttribute('data-theme', 'light');
    }
    loadPresets();
});