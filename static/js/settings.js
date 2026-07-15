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

function createNewPreset() {
    document.getElementById("new-preset-filename").value = "";
    document.getElementById("addPresetModal").classList.add("active");
    setTimeout(() => document.getElementById("new-preset-filename").focus(), 100);
}

function closeAddPresetModal() {
    document.getElementById("addPresetModal").classList.remove("active");
}

async function confirmAddPreset() {
    const filename = document.getElementById("new-preset-filename").value.trim();
    if (!filename) {
        alert("Введите имя файла");
        return;
    }
    
    try {
        const res = await fetch("/api/settings/configs/new", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({filename})
        });
        if (res.ok) {
            closeAddPresetModal();
            await loadPresets();
            changePreset(filename.endsWith(".json") ? filename : filename + ".json");
        } else {
            const err = await res.json();
            alert("Ошибка: " + err.detail);
        }
    } catch(e) { alert(e); }
}

async function deleteCurrentPreset() {
    if (!currentPresetName || currentPresetName === "legacy_default.json") {
        alert("Нельзя удалить этот пресет.");
        return;
    }
    showConfirmDeleteModal(`Вы уверены, что хотите удалить пресет ${currentPresetName} с диска?`, async () => {
        try {
            const res = await fetch("/api/settings/configs/" + currentPresetName, { method: "DELETE" });
            if (res.ok) {
                await loadPresets();
            } else {
                const err = await res.json();
                alert("Ошибка: " + err.detail);
            }
        } catch(e) { alert(e); }
    });
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

    // Кнопка добавления категории
    const addCatBtn = document.createElement("div");
    addCatBtn.className = "tab-item";
    addCatBtn.style.color = "#10b981";
    addCatBtn.innerHTML = "<b>+ Добавить категорию</b>";
    addCatBtn.onclick = addNewCategory;
    sidebar.appendChild(addCatBtn);

    // Вкладка Raw JSON
    sidebar.appendChild(createTabEl("raw", "💻 Файл пресета"));
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

function addNewCategory() {
    if (!currentPresetData.categories) {
        currentPresetData.categories = [];
    }
    const newId = `Cat_${currentPresetData.categories.length + 1}`;
    const newCat = {
        id: newId,
        name: `Новая категория ${currentPresetData.categories.length + 1}`,
        weight: 0.0,
        stop_factors: [],
        features: []
    };
    currentPresetData.categories.push(newCat);
    renderSidebar();
    selectTab(`cat_${currentPresetData.categories.length - 1}`);
}

let deleteActionCallback = null;

function showConfirmDeleteModal(text, callback) {
    document.getElementById("confirmDeleteText").textContent = text;
    deleteActionCallback = callback;
    document.getElementById("confirmDeleteModal").classList.add("active");
    
    document.getElementById("confirmDeleteBtn").onclick = () => {
        if (deleteActionCallback) deleteActionCallback();
        closeConfirmDeleteModal();
    };
}

function closeConfirmDeleteModal() {
    document.getElementById("confirmDeleteModal").classList.remove("active");
    deleteActionCallback = null;
}

function deleteCategory(catIndex) {
    showConfirmDeleteModal(`Вы уверены, что хотите удалить категорию "${currentPresetData.categories[catIndex].name || currentPresetData.categories[catIndex].id}" и все её признаки?`, () => {
        currentPresetData.categories.splice(catIndex, 1);
        renderSidebar();
        selectTab("general");
    });
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
    const segHeader = createSection("Сегментация");
    const addSegBtn = document.createElement("button");
    addSegBtn.textContent = "+ Добавить сегмент";
    addSegBtn.className = "nav-btn";
    addSegBtn.style.marginBottom = "16px";
    addSegBtn.style.marginLeft = "16px";
    addSegBtn.onclick = () => {
        if (!currentPresetData.segments) currentPresetData.segments = {};
        const newKey = "new_segment_" + Date.now();
        currentPresetData.segments[newKey] = { label: "Новый сегмент", min_score: 0 };
        selectTab("general");
    };
    const segHeaderWrap = document.createElement("div");
    segHeaderWrap.style.display = "flex";
    segHeaderWrap.style.alignItems = "center";
    segHeaderWrap.appendChild(segHeader);
    segHeaderWrap.appendChild(addSegBtn);
    container.appendChild(segHeaderWrap);

    for (const [key, seg] of Object.entries(currentPresetData.segments || {})) {
        const row = document.createElement("div");
        row.className = "form-row";
        
        const keyInput = document.createElement("input");
        keyInput.className = "form-input";
        keyInput.value = key;
        keyInput.style.maxWidth = "120px";
        keyInput.onchange = (e) => {
            const newKey = e.target.value;
            if (newKey && newKey !== key) {
                currentPresetData.segments[newKey] = currentPresetData.segments[key];
                delete currentPresetData.segments[key];
                selectTab("general");
            }
        };

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
        
        const delBtn = document.createElement("button");
        delBtn.textContent = "✕";
        delBtn.style.background = "none";
        delBtn.style.border = "none";
        delBtn.style.color = "#ef4444";
        delBtn.style.cursor = "pointer";
        delBtn.onclick = () => {
            delete currentPresetData.segments[key];
            selectTab("general");
        };

        row.appendChild(keyInput);
        row.appendChild(labelInput);
        row.appendChild(scoreInput);
        row.appendChild(delBtn);
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
    const headerRow = document.createElement("div");
    headerRow.style.display = "flex";
    headerRow.style.justifyContent = "space-between";
    headerRow.style.alignItems = "center";
    
    const delCatBtn = document.createElement("button");
    delCatBtn.textContent = "Удалить категорию";
    delCatBtn.className = "nav-btn";
    delCatBtn.style.color = "#ef4444";
    delCatBtn.style.borderColor = "#ef4444";
    delCatBtn.onclick = () => deleteCategory(catIndex);
    
    headerRow.appendChild(createInputRow("Идентификатор", category.id, (val) => category.id = val));
    headerRow.appendChild(delCatBtn);
    container.appendChild(headerRow);
    
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

    // Стоп-факторы
    container.appendChild(createSection(`Стоп-факторы (${category.stop_factors ? category.stop_factors.length : 0})`));
    const addSfBtn = document.createElement("button");
    addSfBtn.textContent = "+ Добавить стоп-фактор";
    addSfBtn.className = "nav-btn";
    addSfBtn.style.marginBottom = "16px";
    addSfBtn.onclick = () => showAddStopFactorModal(category, catIndex);
    container.appendChild(addSfBtn);

    const sfContainer = document.createElement("div");
    sfContainer.style.background = "var(--glass-bg)";
    sfContainer.style.border = "1px solid var(--border-color)";
    sfContainer.style.borderRadius = "8px";
    sfContainer.style.padding = "16px";
    sfContainer.style.marginBottom = "24px";
    sfContainer.style.display = "flex";
    sfContainer.style.flexDirection = "column";
    sfContainer.style.gap = "8px";

    (category.stop_factors || []).forEach((sf, sfIndex) => {
        const row = document.createElement("div");
        row.style.display = "flex";
        row.style.gap = "8px";
        row.style.alignItems = "center";
        row.style.background = "var(--bg-color)";
        row.style.padding = "8px";
        row.style.borderRadius = "4px";
        row.style.border = "1px solid var(--border-color)";

        const typeLabel = document.createElement("div");
        typeLabel.style.fontSize = "12px";
        typeLabel.style.fontWeight = "bold";
        typeLabel.style.width = "120px";
        typeLabel.textContent = sf.type;
        row.appendChild(typeLabel);

        const idInput = document.createElement("input");
        idInput.className = "form-input";
        idInput.placeholder = "ID признака";
        idInput.value = sf.feature_id || "";
        idInput.onchange = (e) => sf.feature_id = e.target.value;
        row.appendChild(idInput);

        if (sf.type === "exact_value") {
            const valInput = document.createElement("input");
            valInput.className = "form-input";
            valInput.placeholder = "Значение (value)";
            valInput.value = sf.value !== undefined ? sf.value : "";
            valInput.onchange = (e) => sf.value = e.target.value;
            row.appendChild(valInput);
        } else if (sf.type === "numeric_condition") {
            const opSelect = document.createElement("select");
            opSelect.className = "form-input";
            opSelect.style.maxWidth = "80px";
            ["<", "<=", "==", ">=", ">"].forEach(op => {
                const opt = document.createElement("option");
                opt.value = op;
                opt.textContent = op;
                opSelect.appendChild(opt);
            });
            opSelect.value = sf.operator || "==";
            opSelect.onchange = (e) => sf.operator = e.target.value;
            row.appendChild(opSelect);

            const valInput = document.createElement("input");
            valInput.className = "form-input";
            valInput.type = "number";
            valInput.placeholder = "Значение";
            valInput.value = sf.value !== undefined ? sf.value : "";
            valInput.onchange = (e) => sf.value = Number(e.target.value);
            row.appendChild(valInput);
        } else if (sf.type === "present") {
            const flagSelect = document.createElement("select");
            flagSelect.className = "form-input";
            flagSelect.innerHTML = `<option value="true">Да (true)</option><option value="false">Нет (false)</option>`;
            flagSelect.value = sf.flag !== undefined ? sf.flag.toString() : "true";
            flagSelect.onchange = (e) => sf.flag = e.target.value === "true";
            row.appendChild(flagSelect);
        } else {
            const info = document.createElement("div");
            info.style.flex = "1";
            info.style.fontSize = "12px";
            info.style.color = "var(--text-secondary)";
            info.textContent = "Редактируйте параметры в Raw JSON";
            row.appendChild(info);
        }

        const delBtn = document.createElement("button");
        delBtn.textContent = "✕";
        delBtn.style.background = "none";
        delBtn.style.border = "none";
        delBtn.style.color = "#ef4444";
        delBtn.style.cursor = "pointer";
        delBtn.onclick = () => {
            category.stop_factors.splice(sfIndex, 1);
            selectTab(`cat_${catIndex}`);
        };
        row.appendChild(delBtn);

        sfContainer.appendChild(row);
    });
    if ((category.stop_factors || []).length > 0) {
        container.appendChild(sfContainer);
    }

    container.appendChild(createSection(`Параметры признаков (${category.features ? category.features.length : 0})`));

    const addFeatBtn = document.createElement("button");
    addFeatBtn.textContent = "+ Добавить признак";
    addFeatBtn.className = "nav-btn";
    addFeatBtn.style.marginBottom = "16px";
    addFeatBtn.style.background = "var(--primary-gradient)";
    addFeatBtn.style.color = "white";
    addFeatBtn.onclick = () => showAddFeatureModal(category, catIndex);
    container.appendChild(addFeatBtn);

    (category.features || []).forEach((feat, fIndex) => {
        const card = document.createElement("div");
        card.className = "feature-card";

        const header = document.createElement("div");
        header.className = "feature-header";
        const fTypeSlug = feat.scoring_method ? feat.scoring_method.type : "unknown";
        const typeLabels = {
            "binary_presence": "Бинарное наличие",
            "categorical_mapping": "Сопоставление (Словарь/Диапазоны)",
            "log_scale": "Логарифмическая шкала",
            "log_score_simple": "Простая шкала",
            "percentile_rank": "Перцентильный ранг",
            "debt_ratio": "Долговая нагрузка",
            "okved_mapping": "Маппинг ОКВЭД",
            "tax_mapping": "Маппинг Налогов"
        };
        const fTypeLabel = typeLabels[fTypeSlug] || fTypeSlug;
        
        header.innerHTML = `Признак: <span>${feat.name || feat.id}</span> <span style="font-size: 11px; font-weight: normal; color: var(--text-secondary); background: var(--glass-bg); padding: 2px 6px; border-radius: 4px; margin-left: 8px; border: 1px solid var(--border-color);">${fTypeLabel}</span>`;
        card.appendChild(header);

        card.appendChild(createInputRow("Название", feat.name || "", (val) => {
            feat.name = val;
            header.querySelector("span").textContent = val;
        }));
        card.appendChild(createInputRow("Идентификатор", feat.id, (val) => feat.id = val));
        
        // ВЕС УБРАН ИЗ КАРТОЧКИ, так как он редактируется в верхнем блоке

        if (feat.scoring_method && feat.scoring_method.params) {
            const p = feat.scoring_method.params;
            if (p.threshold !== undefined) {
                card.appendChild(createInputRow("Порог", p.threshold, (val) => p.threshold = Number(val), "number"));
            }
            if (p.scale !== undefined) {
                card.appendChild(createInputRow("Шкала", p.scale, (val) => p.scale = Number(val), "number"));
            }
            if (p.apply_regional_coeff !== undefined) {
                const regRow = document.createElement("div");
                regRow.className = "form-row";
                const regLabel = document.createElement("div");
                regLabel.className = "form-label";
                regLabel.textContent = "Учитывать регион (apply_regional_coeff)";
                const regInput = document.createElement("input");
                regInput.type = "checkbox";
                regInput.checked = p.apply_regional_coeff === "true" || p.apply_regional_coeff === true;
                regInput.onchange = (e) => p.apply_regional_coeff = e.target.checked;
                regRow.appendChild(regLabel);
                regRow.appendChild(regInput);
                card.appendChild(regRow);
            }
            if (p.revenue_feature !== undefined) {
                card.appendChild(createInputRow("ID признака выручки", p.revenue_feature, (val) => p.revenue_feature = val));
            }
            if (p.present !== undefined) {
                card.appendChild(createInputRow("Балл (Присутствует)", p.present, (val) => p.present = Number(val), "number"));
            }
            if (p.absent !== undefined) {
                card.appendChild(createInputRow("Балл (Отсутствует)", p.absent, (val) => p.absent = Number(val), "number"));
            }
            if (p.cap !== undefined) {
                card.appendChild(createInputRow("Макс. балл", p.cap, (val) => p.cap = Number(val), "number"));
            }
            if (p.special_one !== undefined) {
                card.appendChild(createInputRow("Балл (Если значение = 1)", p.special_one, (val) => p.special_one = Number(val), "number"));
            }
            if (p.default_score !== undefined) {
                card.appendChild(createInputRow("Балл по умолчанию (Не найдено)", p.default_score, (val) => p.default_score = Number(val), "number"));
            }
            if (p.empty_score !== undefined) {
                card.appendChild(createInputRow("Балл (Пустая ячейка)", p.empty_score, (val) => p.empty_score = Number(val), "number"));
            }
            if (p.mapping !== undefined) {
                // Выбор типа маппинга (exact, starts_with, contains, range)
                const mtRow = document.createElement("div");
                mtRow.className = "form-row";
                mtRow.style.marginTop = "12px";
                const mtLabel = document.createElement("div");
                mtLabel.className = "form-label";
                mtLabel.textContent = "Правило поиска";
                
                const mtSelect = document.createElement("select");
                mtSelect.className = "form-input";
                mtSelect.innerHTML = `
                    <option value="exact">Точное совпадение</option>
                    <option value="starts_with">Начинается с (например, ОКВЭД)</option>
                    <option value="contains">Содержит</option>
                    <option value="range">Числовой промежуток</option>
                `;
                mtSelect.value = p.match_type || "exact";
                
                // Tooltip для числовых промежутков
                const tooltipInfo = document.createElement("div");
                tooltipInfo.className = "tooltip";
                tooltipInfo.textContent = "i";
                tooltipInfo.style.display = mtSelect.value === "range" ? "inline-flex" : "none";
                tooltipInfo.innerHTML = `i<span class="tooltip-text"><b>Правила для промежутков:</b><br/>• 10-20 (от 10 до 20 включительно)<br/>• &lt;10 (строго меньше 10)<br/>• &lt;=10 (меньше или равно)<br/>• &gt;50 (строго больше 50)<br/>• &gt;=50 (больше или равно)<br/>• 15 (точно равно 15)</span>`;
                
                mtSelect.onchange = (e) => {
                    p.match_type = e.target.value;
                    tooltipInfo.style.display = p.match_type === "range" ? "inline-flex" : "none";
                };

                const selectWrapper = document.createElement("div");
                selectWrapper.style.display = "flex";
                selectWrapper.style.alignItems = "center";
                selectWrapper.style.flex = "1";
                selectWrapper.appendChild(mtSelect);
                selectWrapper.appendChild(tooltipInfo);
                
                mtRow.appendChild(mtLabel);
                mtRow.appendChild(selectWrapper);
                card.appendChild(mtRow);

                // Чекбокс учета регистра
                const csRow = document.createElement("div");
                csRow.className = "form-row";
                const csLabel = document.createElement("div");
                csLabel.className = "form-label";
                csLabel.textContent = "Учитывать регистр (A ≠ a)";
                
                const csInput = document.createElement("input");
                csInput.type = "checkbox";
                csInput.checked = p.case_sensitive || false;
                csInput.onchange = (e) => p.case_sensitive = e.target.checked;
                
                csRow.appendChild(csLabel);
                csRow.appendChild(csInput);
                card.appendChild(csRow);

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

        const delFeatBtn = document.createElement("button");
        delFeatBtn.textContent = "Удалить признак";
        delFeatBtn.style.marginTop = "12px";
        delFeatBtn.style.color = "#ef4444";
        delFeatBtn.style.background = "none";
        delFeatBtn.style.border = "1px solid #ef4444";
        delFeatBtn.style.padding = "4px 8px";
        delFeatBtn.style.borderRadius = "4px";
        delFeatBtn.style.cursor = "pointer";
        delFeatBtn.onclick = () => {
            showConfirmDeleteModal(`Удалить признак "${feat.name || feat.id}"?`, () => {
                category.features.splice(fIndex, 1);
                selectTab(`cat_${catIndex}`); // Ре-рендер
            });
        };
        card.appendChild(delFeatBtn);

        container.appendChild(card);
    });
}

let tempAddFeatureCat = null;
let tempAddFeatureCatIndex = null;

function showAddFeatureModal(category, catIndex) {
    tempAddFeatureCat = category;
    tempAddFeatureCatIndex = catIndex;
    document.getElementById("addFeatureModal").classList.add("active");
}

function closeAddFeatureModal() {
    document.getElementById("addFeatureModal").classList.remove("active");
    tempAddFeatureCat = null;
    tempAddFeatureCatIndex = null;
}

function confirmAddFeature() {
    if (!tempAddFeatureCat) return;
    
    const type = document.getElementById("feature-type-select").value;
    const category = tempAddFeatureCat;
    const catIndex = tempAddFeatureCatIndex;

    if (!category.features) category.features = [];
    const newFeatId = `feat_${category.features.length + 1}`;
    const newFeat = {
        id: newFeatId,
        name: `Новый признак ${category.features.length + 1}`,
        weight: 0.0,
        scoring_method: { type: type, params: {} }
    };

    if (type === "binary_presence") newFeat.scoring_method.params = { present: 100, absent: 0 };
    if (type === "log_scale") newFeat.scoring_method.params = { threshold: 1000000, scale: 20, apply_regional_coeff: false };
    if (type === "categorical_mapping") newFeat.scoring_method.params = { mapping: {}, default_score: 0, empty_score: 0, match_type: "exact", case_sensitive: false };
    if (type === "log_score_simple") newFeat.scoring_method.params = { cap: 100, special_one: 1 };
    if (type === "debt_ratio") newFeat.scoring_method.params = { threshold: 0.3, revenue_feature: "revenue" };

    category.features.push(newFeat);
    
    closeAddFeatureModal();
    selectTab(`cat_${catIndex}`); // Перерисовка текущей вкладки
}

let tempSfCat = null;
let tempSfCatIndex = null;

function showAddStopFactorModal(category, catIndex) {
    tempSfCat = category;
    tempSfCatIndex = catIndex;
    document.getElementById("addStopFactorModal").classList.add("active");
}

function closeAddStopFactorModal() {
    document.getElementById("addStopFactorModal").classList.remove("active");
    tempSfCat = null;
    tempSfCatIndex = null;
}

function confirmAddStopFactor() {
    if (!tempSfCat) return;
    const type = document.getElementById("stop-factor-type-select").value;
    
    if (!tempSfCat.stop_factors) tempSfCat.stop_factors = [];
    const newSf = { type: type, feature_id: "new_feature_id" };
    
    if (type === "exact_value") {
        newSf.value = "строка_или_число";
    } else if (type === "numeric_condition") {
        newSf.operator = ">";
        newSf.value = 0;
    } else if (type === "present") {
        newSf.flag = true;
    }
    
    tempSfCat.stop_factors.push(newSf);
    closeAddStopFactorModal();
    selectTab(`cat_${tempSfCatIndex}`);
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
        if (!c.features || c.features.length === 0) return;
        let featSum = 0;
        c.features.forEach(f => featSum += (f.weight || 0));
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
            const err = await res.json();
            statusEl.textContent = "❌ Ошибка сервера";
            statusEl.style.color = "#ef4444";
            alert("Ошибка сохранения:\n" + err.detail);
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