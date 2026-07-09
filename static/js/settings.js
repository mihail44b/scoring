const TRANSLATIONS = {
    // Названия файлов
    "weights.json": "Общие веса и сегменты",
    "category_a_config.json": "Категория А: Финансовое здоровье",
    "category_b_config.json": "Категория B: Масштаб",
    "category_d_config.json": "Категория D: Контакты",
    "category_e_config.json": "Категория E: Юр. статус",
    "enrichment_weights.json": "Веса обогащения (Enrichment)",
    "okved_tiers.json": "Справочник ОКВЭД (коды и баллы)",
    "tax_regimes.json": "Справочник Налогов (режимы и баллы)",
    
    // Блоки
    "categories": "Категории скоринга",
    "segments": "Сегментация (Горячий/Теплый/Холодный)",
    "features": "Веса внутренних признаков",
    "thresholds": "Пороги отсечения (в рублях)",
    "log_scale": "Множители логарифмической шкалы",
    "regional_coefficients": "Региональные множители (снижение порогов)",
    "column_map": "Привязка колонок из Excel",
    "rmsp_mapping": "Баллы за категорию РМСП",
    "default_scores": "Баллы по умолчанию",

    // Категории
    "A_financial_health": "Категория А",
    "B_scale_maturity": "Категория B",
    "C_industry_relevance": "Категория C",
    "D_contact_availability": "Категория D",
    "E_legal_status": "Категория E",

    // Признаки
    "weight": "Общий вес категории (от 0 до 1)",
    "name": "Отображаемое название",
    "comment": "Комментарий",
    "revenue": "Выручка",
    "fixed_assets": "Основные средства",
    "charter_capital": "Уставной капитал",
    "net_profit": "Чистая прибыль",
    "operating_profit": "Прибыль от продаж",
    "pretax_profit": "Прибыль до налогообложения",
    "debt_kz": "Кредиторская задолженность",
    "debt_dz": "Дебиторская задолженность",
    "debt_kz_ratio": "Порог КЗ/Выручка",
    "debt_dz_ratio": "Порог ДЗ/Выручка",
    "чуваш": "Чувашская Республика (множитель)",
    "registration": "Дата регистрации",
    "rmsp": "Статус РМСП",
    "employees": "Кол-во сотрудников",
    "reserves": "Запасы",
    "okved": "ОКВЭД",
    "tax_regime": "Налоговый режим",
    "phone": "Телефон",
    "email": "Email",
    "website": "Сайт",
    "address": "Адрес",
    "manager": "ФИО Руководителя",
    "position": "Должность",
    "liquidation": "Стадия ликвидации",
    "okfs": "ОКФС",
    "okopf": "ОКОПФ",
    "inn_manager": "ИНН Руководителя",
    "Микропредприятие": "Микропредприятие",
    "Малое предприятие": "Малое предприятие",
    "Среднее предприятие": "Среднее предприятие",
    
    // Сегменты
    "hot": "Горячий",
    "warm": "Тёплый",
    "cold": "Холодный",
    "min_score": "Минимальный балл",
    "label": "Метка сегмента",

    // Справочники
    "okfs.json": "Справочник ОКФС (коды и баллы)",
    "okopf.json": "Справочник ОКОПФ (коды и баллы)"
};

const DICTIONARY_FILES = [
    "okved_tiers.json", 
    "tax_regimes.json", 
    "okfs.json", 
    "okopf.json"
];

let configs = {};
let currentFile = null;

async function loadConfigs() {
    try {
        const response = await fetch('/api/settings/configs');
        configs = await response.json();
        renderSidebar();
    } catch (e) {
        console.error("Ошибка загрузки:", e);
    }
}

function t(key) {
    return TRANSLATIONS[key] || key;
}

function renderSidebar() {
    const sidebar = document.getElementById("file-list");
    sidebar.innerHTML = "";
    
    const filenames = Object.keys(configs).sort((a, b) => {
        if(a === 'weights.json') return -1;
        if(b === 'weights.json') return 1;
        return a.localeCompare(b);
    });

    filenames.forEach(file => {
        const div = document.createElement("div");
        div.className = "file-item";
        div.innerHTML = `
            <span class="file-name">${t(file)}</span>
            <span class="file-desc">${file}</span>
        `;
        div.onclick = () => selectFile(file, div);
        sidebar.appendChild(div);
    });

    if (filenames.length > 0) {
        selectFile(filenames[0], sidebar.firstChild);
    }
}

function selectFile(filename, element) {
    document.querySelectorAll(".file-item").forEach(el => el.classList.remove("active"));
    if (element) element.classList.add("active");
    
    currentFile = filename;
    document.getElementById("current-title").textContent = t(filename);
    
    renderForm(configs[filename]);
}

function createInputRow(key, value, path) {
    const row = document.createElement("div");
    row.className = "form-row";
    
    const label = document.createElement("div");
    label.className = "form-label";
    label.textContent = t(key);
    
    const input = document.createElement("input");
    input.className = "form-input";
    input.dataset.path = path.join("."); // Путь для сборки обратно
    
    if (typeof value === "number") {
        input.type = "number";
        input.step = "any"; // разрешаем дробные
        input.value = value;
    } else {
        input.type = "text";
        input.value = value;
    }
    
    row.appendChild(label);
    row.appendChild(input);
    return row;
}

function buildFormRecursive(obj, container, path = []) {
    for (const key in obj) {
        const val = obj[key];
        
        if (typeof val === "object" && val !== null) {
            const section = document.createElement("div");
            if (path.length > 0 || isNaN(key)) {
                const title = document.createElement("div");
                title.className = "section-title";
                title.textContent = t(key);
                section.appendChild(title);
            }
            const content = document.createElement("div");
            content.className = "form-group";
            buildFormRecursive(val, content, [...path, key]);
            section.appendChild(content);
            container.appendChild(section);
        } else {
            const row = createInputRow(key, val, [...path, key]);
            container.appendChild(row);
        }
    }
}

// ─── ЛОГИКА ДЛЯ СПРАВОЧНИКОВ ────────────────────────────────────────────────

function createDictRow(key, val) {
    const row = document.createElement("div");
    row.className = "form-row dict-row";
    row.style.marginBottom = "8px";
    
    const keyInput = document.createElement("input");
    keyInput.className = "form-input dict-key";
    keyInput.type = "text";
    keyInput.value = key;
    keyInput.placeholder = "Ключ (код)";
    keyInput.style.maxWidth = "180px";
    
    const valInput = document.createElement("input");
    valInput.className = "form-input dict-val";
    valInput.type = "number";
    valInput.step = "any";
    valInput.value = val;
    valInput.placeholder = "Балл";
    valInput.style.maxWidth = "100px";
    
    const delBtn = document.createElement("button");
    delBtn.innerHTML = "❌";
    delBtn.style.background = "none";
    delBtn.style.border = "none";
    delBtn.style.cursor = "pointer";
    delBtn.style.fontSize = "16px";
    delBtn.style.padding = "4px";
    delBtn.onclick = () => row.remove();
    
    row.appendChild(keyInput);
    row.appendChild(valInput);
    row.appendChild(delBtn);
    return row;
}

function renderDictionaryForm(configData, container) {
    const title = document.createElement("div");
    title.className = "section-title";
    title.textContent = "Редактирование справочника (Код - Балл)";
    title.style.display = "flex";
    title.style.justifyContent = "space-between";
    
    const addBtn = document.createElement("button");
    addBtn.textContent = "+ Добавить запись";
    addBtn.className = "btn-save";
    addBtn.style.padding = "6px 12px";
    addBtn.style.fontSize = "13px";
    addBtn.onclick = () => {
        const newRow = createDictRow("", 0);
        dictContainer.insertBefore(newRow, dictContainer.firstChild); // Добавляем наверх
    };
    title.appendChild(addBtn);
    container.appendChild(title);

    const dictContainer = document.createElement("div");
    dictContainer.className = "form-group";
    
    // Сортируем ключи по алфавиту для удобства
    const sortedKeys = Object.keys(configData).sort((a, b) => a.localeCompare(b));
    sortedKeys.forEach(key => {
        dictContainer.appendChild(createDictRow(key, configData[key]));
    });
    
    container.appendChild(dictContainer);
}

function renderForm(configData) {
    const container = document.getElementById("form-container");
    container.innerHTML = "";
    
    if (DICTIONARY_FILES.includes(currentFile)) {
        renderDictionaryForm(configData, container);
    } else {
        buildFormRecursive(configData, container);
    }
}

function setNestedValue(obj, pathArr, value) {
    let current = obj;
    for (let i = 0; i < pathArr.length - 1; i++) {
        if (!current[pathArr[i]]) current[pathArr[i]] = {};
        current = current[pathArr[i]];
    }
    const lastKey = pathArr[pathArr.length - 1];
    current[lastKey] = value;
}

async function saveConfig() {
    if (!currentFile) return;
    
    let newData;
    
    if (DICTIONARY_FILES.includes(currentFile)) {
        newData = {};
        document.querySelectorAll(".dict-row").forEach(row => {
            const key = row.querySelector(".dict-key").value.trim();
            const val = row.querySelector(".dict-val").value;
            if (key !== "") {
                newData[key] = val !== "" ? Number(val) : 0;
            }
        });
    } else {
        newData = JSON.parse(JSON.stringify(configs[currentFile])); // глубокая копия
        const inputs = document.querySelectorAll(".form-input:not(.dict-key):not(.dict-val)");
        inputs.forEach(input => {
            if (!input.dataset.path) return;
            const pathArr = input.dataset.path.split(".");
            let val = input.value;
            if (input.type === "number") {
                val = val !== "" ? Number(val) : null;
            }
            setNestedValue(newData, pathArr, val);
        });
    }
    
    configs[currentFile] = newData;
    
    // Отправка на сервер
    const payload = {};
    payload[currentFile] = newData;
    
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
            statusEl.style.color = "var(--color-cold)";
        } else {
            statusEl.textContent = "❌ Ошибка сервера";
            statusEl.style.color = "var(--color-hot)";
        }
    } catch (e) {
        statusEl.textContent = "❌ Ошибка сети";
        statusEl.style.color = "var(--color-hot)";
    }
    
    setTimeout(() => { statusEl.style.display = "none"; }, 3000);
}

// Переключение темы (копия логики из index)
function toggleTheme() {
    const root = document.documentElement;
    const currentTheme = root.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    document.getElementById('themeToggleBtn').innerHTML = newTheme === 'dark' ? '☀️ Светлая тема' : '🌙 Тёмная тема';
}

document.addEventListener("DOMContentLoaded", () => {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
        document.documentElement.setAttribute('data-theme', savedTheme);
        document.getElementById('themeToggleBtn').innerHTML = savedTheme === 'dark' ? '☀️ Светлая тема' : '🌙 Тёмная тема';
    }
    loadConfigs();
});
