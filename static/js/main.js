/* ============================================================
   Скоринг ДП — дашборд (main.js)
   ============================================================ */

let currentTheme = localStorage.getItem('theme') || 'light';
document.documentElement.setAttribute('data-theme', currentTheme);
updateThemeButtonUI();

let dashboardData = null;
let originalFile = null;
let categoryChartInstance = null;
const CATEGORY_LABELS = { A: 'Фин. здоровье', B: 'Масштаб', C: 'Отрасль', D: 'Контакты', E: 'Юр. статус' };

const filters = {
    search: '',
    segment: '',
    region: '',
    quality: '',
    stopMode: 'all', // all | without | only
};
let categoryChartMode = 'all'; // all | without | only

// ─── Тема ───────────────────────────────────────────────────────────────

function toggleTheme() {
    currentTheme = currentTheme === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', currentTheme);
    localStorage.setItem('theme', currentTheme);
    updateThemeButtonUI();
    if (dashboardData) renderCategoryChart();
}

function updateThemeButtonUI() {
    const btn = document.getElementById('themeToggleBtn');
    btn.innerText = currentTheme === 'light' ? 'Тёмная тема' : 'Светлая тема';
}

// ─── Загрузка файла ────────────────────────────────────────────────────

async function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    originalFile = file;

    const status = document.getElementById('upload-status');
    const spinner = document.getElementById('spinner-overlay');
    status.innerText = '';
    spinner.style.display = 'flex';

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/api/score/full', { method: 'POST', body: formData });

        if (res.ok) {
            const data = await res.json();
            dashboardData = data;

            document.getElementById('upload-panel').style.display = 'none';
            document.getElementById('dashboard').style.display = 'flex';

            const fileDisplay = document.getElementById('file-name-display');
            fileDisplay.innerText = `Файл: ${file.name}`;
            fileDisplay.style.display = 'inline';

            populateRegionFilterOptions();
            renderDashboard();
        } else {
            const err = await res.json();
            status.innerText = `Ошибка расчёта: ${err.detail || 'Неизвестная ошибка'}`;
        }
    } catch (e) {
        console.error(e);
        status.innerText = 'Сетевая ошибка при отправке файла.';
    } finally {
        spinner.style.display = 'none';
    }
}

function renderDashboard() {
    populateSummary(dashboardData.stats);
    populateSegments(dashboardData.stats);
    renderCategoryChart();
    renderRegionList();
    applyFilters();
}

// ─── Сводная строка ────────────────────────────────────────────────────

function populateSummary(stats) {
    document.getElementById('kpi-total').innerText = stats.total;
    document.getElementById('kpi-avg').innerText = (stats.averages.total || 0).toFixed(1);

    const stoppedTotal = stats.stops.total_companies_stopped ?? 0;
    document.getElementById('kpi-stops').innerText = stoppedTotal;
    const byCat = stats.stops.by_category || {};
    const parts = Object.entries(byCat).filter(([, v]) => v > 0).map(([k, v]) => `${k}: ${v}`);
    document.getElementById('kpi-stops-sub').innerText = parts.length ? parts.join(' · ') : 'не обнаружены';

    const qd = stats.quality_distribution || {};
    const needEnrich = (dashboardData.records || []).filter(r => r.ui_needs_enrichment).length;
    document.getElementById('kpi-enrich').innerText = needEnrich;
}

// ─── Температурные сегменты ────────────────────────────────────────────

function populateSegments(stats) {
    const total = stats.total || 1;
    const segMap = { hot: 'Горячий', warm: 'Тёплый', cold: 'Холодный' };

    Object.entries(segMap).forEach(([key, label]) => {
        const count = stats.segments[label] || 0;
        const share = Math.round((count / total) * 100);
        const avg = stats.segment_avg_score ? (stats.segment_avg_score[label] || 0) : 0;

        document.getElementById(`seg-${key}-count`).innerText = count;
        document.getElementById(`seg-${key}-share`).innerText = `${share}%`;
        document.getElementById(`seg-${key}-bar`).style.width = `${share}%`;
        document.getElementById(`seg-${key}-avg`).innerText = avg.toFixed(1);
    });
}

function toggleSegmentFilter(label) {
    filters.segment = filters.segment === label ? '' : label;
    document.getElementById('segmentFilter').value = filters.segment;
    highlightActiveSegmentCard();
    applyFilters();
}

function onSegmentSelectChange() {
    filters.segment = document.getElementById('segmentFilter').value;
    highlightActiveSegmentCard();
    applyFilters();
}

function highlightActiveSegmentCard() {
    const map = { 'Горячий': 'seg-hot', 'Тёплый': 'seg-warm', 'Холодный': 'seg-cold' };
    ['seg-hot', 'seg-warm', 'seg-cold'].forEach(id => document.getElementById(id).classList.remove('active'));
    if (filters.segment && map[filters.segment]) {
        document.getElementById(map[filters.segment]).classList.add('active');
    }
}

// ─── График средних баллов по категориям ───────────────────────────────

function setCategoryMode(mode) {
    categoryChartMode = mode;
    document.querySelectorAll('#catStopToggle button').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
    renderCategoryChart();
}

function computeCategoryAverages(mode) {
    const records = (dashboardData && dashboardData.records) || [];
    const filtered = records.filter(r => {
        if (mode === 'without') return !r.ui_any_stop;
        if (mode === 'only') return r.ui_any_stop;
        return true;
    });
    const ids = Object.keys(CATEGORY_LABELS);
    const sums = {}; const counts = {};
    ids.forEach(id => { sums[id] = 0; counts[id] = 0; });
    filtered.forEach(r => {
        ids.forEach(id => {
            const v = r[`${id}_score`];
            if (v !== null && v !== undefined) { sums[id] += v; counts[id] += 1; }
        });
    });
    const averages = ids.map(id => counts[id] ? Math.round((sums[id] / counts[id]) * 10) / 10 : 0);
    return { ids, averages, n: filtered.length };
}

const valueLabelsPlugin = {
    id: 'valueLabels',
    afterDatasetsDraw(chart) {
        const { ctx } = chart;
        const meta = chart.getDatasetMeta(0);
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        ctx.save();
        ctx.fillStyle = isDark ? '#eef1f8' : '#10182b';
        ctx.font = "700 12px 'IBM Plex Mono', monospace";
        ctx.textAlign = 'center';
        meta.data.forEach((bar, i) => {
            const val = chart.data.datasets[0].data[i];
            ctx.fillText(val.toFixed(1), bar.x, bar.y - 8);
        });
        ctx.restore();
    }
};

function renderCategoryChart() {
    if (!dashboardData) return;
    const isDark = currentTheme === 'dark';
    const textColor = isDark ? '#9aa4bd' : '#5b6479';
    const gridColor = isDark ? '#263248' : '#e1e5ee';

    const { ids, averages, n } = computeCategoryAverages(categoryChartMode);
    document.querySelector('#categoryChart').closest('.chart-box').querySelector('.chart-hint').innerText =
        `Метки — среднее по категориям · выборка: ${n} компаний`;

    if (categoryChartInstance) categoryChartInstance.destroy();
    const ctx = document.getElementById('categoryChart').getContext('2d');
    categoryChartInstance = new Chart(ctx, {
        type: 'bar',
        plugins: [valueLabelsPlugin],
        data: {
            labels: ids.map(id => `${id} · ${CATEGORY_LABELS[id]}`),
            datasets: [{
                data: averages,
                backgroundColor: isDark ? 'rgba(94,143,214,0.55)' : 'rgba(42,77,143,0.75)',
                borderRadius: 4,
                maxBarThickness: 46,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { top: 22 } },
            plugins: { legend: { display: false }, tooltip: { padding: 10 } },
            scales: {
                y: { min: 0, max: 100, grid: { color: gridColor }, ticks: { color: textColor, font: { size: 11 } } },
                x: { grid: { display: false }, ticks: { color: textColor, font: { size: 11 } } }
            }
        }
    });
}

// ─── Регионы ────────────────────────────────────────────────────────────

function populateRegionFilterOptions() {
    if (!dashboardData) return;
    const regions = Object.entries(dashboardData.stats.regions || {}).sort((a, b) => b[1] - a[1]);

    const filterSel = document.getElementById('regionFilter');
    const jumpSel = document.getElementById('regionJumpSelect');
    filterSel.innerHTML = '<option value="">Все регионы</option>';
    jumpSel.innerHTML = '<option value="">Выбрать регион…</option>';

    regions.forEach(([name, count]) => {
        const o1 = document.createElement('option');
        o1.value = name; o1.textContent = `${name} (${count})`;
        filterSel.appendChild(o1);

        const o2 = document.createElement('option');
        o2.value = name; o2.textContent = `${name} (${count})`;
        jumpSel.appendChild(o2);
    });
}

function jumpToRegion(name) {
    document.getElementById('regionFilter').value = name;
    filters.region = name;
    applyFilters();
}

function renderRegionList() {
    if (!dashboardData) return;
    const regions = Object.entries(dashboardData.stats.regions || {}).sort((a, b) => b[1] - a[1]);
    const topN = Math.max(1, parseInt(document.getElementById('regionTopN').value) || 8);
    const shown = regions.slice(0, topN);
    const maxCount = shown.length ? shown[0][1] : 1;

    document.getElementById('regionsHint').innerText = `${regions.length} регионов определено`;

    const listEl = document.getElementById('region-list');
    listEl.innerHTML = '';
    shown.forEach(([name, count]) => {
        const row = document.createElement('div');
        row.className = 'region-row' + (filters.region === name ? ' active' : '');
        row.onclick = () => jumpToRegion(filters.region === name ? '' : name);
        const pct = Math.round((count / maxCount) * 100);
        row.innerHTML = `
            <div class="r-name" title="${name}">${name}</div>
            <div class="r-bar-bg"><div class="r-bar-fill" style="width:${pct}%;"></div></div>
            <div class="r-count">${count}</div>
        `;
        listEl.appendChild(row);
    });
}

// ─── Фильтры реестра ────────────────────────────────────────────────────

function setStopFilter(mode) {
    filters.stopMode = mode;
    document.querySelectorAll('#stopChipGroup button').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
    applyFilters();
}

function applyFilters() {
    if (!dashboardData) return;

    filters.search = document.getElementById('searchInput').value.toLowerCase().trim();
    filters.region = document.getElementById('regionFilter').value;
    filters.quality = document.getElementById('qualityFilter').value;

    const filtered = dashboardData.records.filter(rec => {
        if (filters.search) {
            const nameMatch = String(rec.ui_name).toLowerCase().includes(filters.search);
            const innMatch = String(rec.ui_inn).toLowerCase().includes(filters.search);
            if (!nameMatch && !innMatch) return false;
        }
        if (filters.segment && rec.scoring_segment !== filters.segment) return false;
        if (filters.region && rec.ui_region !== filters.region) return false;
        if (filters.quality && rec.ui_data_quality_label !== filters.quality) return false;
        if (filters.stopMode === 'without' && rec.ui_any_stop) return false;
        if (filters.stopMode === 'only' && !rec.ui_any_stop) return false;
        return true;
    });

    document.getElementById('resultCount').innerText = `${filtered.length} из ${dashboardData.records.length} записей`;
    renderRegionList();
    populateTable(filtered);
}

// ─── Таблица реестра ────────────────────────────────────────────────────

function segClass(seg) {
    if (seg === 'Горячий') return 'hot';
    if (seg === 'Тёплый') return 'warm';
    return 'cold';
}

function qualityClass(label) {
    if (label === 'Высокое') return 'high';
    if (label === 'Среднее') return 'medium';
    return 'low';
}

function scoreCellHtml(val) {
    if (val === null || val === undefined) return '<span class="score-cell zero">н/д</span>';
    const cls = val === 0 ? 'score-cell zero' : 'score-cell';
    return `<span class="${cls}">${val}</span>`;
}

function contactDotsHtml(rec) {
    const items = [
        { key: 'ui_contact_phone', label: 'Тел' },
        { key: 'ui_contact_email', label: 'Мэйл' },
        { key: 'ui_contact_website', label: 'Веб' },
        { key: 'ui_has_manager', label: 'Рук' },
    ];
    return `<div class="contact-dots">${items.map(it => {
        const present = it.key === 'ui_has_manager' ? !!rec[it.key] : !!(rec[it.key] && rec[it.key].present);
        return `<span class="contact-dot ${present ? 'present' : 'absent'}" title="${it.label}: ${present ? 'есть' : 'нет'}">${it.label[0]}</span>`;
    }).join('')}</div>`;
}

function stopFlagHtml(rec) {
    if (!rec.ui_any_stop) return '<span class="no-stop-flag">—</span>';
    const cats = (rec.ui_stopped_categories || []).join(', ');
    return `<span class="stop-flag" title="Категории: ${cats}">${cats}</span>`;
}

function populateTable(records) {
    const tbody = document.getElementById('table-body');
    tbody.innerHTML = '';

    if (!records.length) {
        tbody.innerHTML = `<tr><td colspan="13" class="empty-state">Нет компаний, соответствующих выбранным фильтрам</td></tr>`;
        return;
    }

    records.forEach(rec => {
        const tr = document.createElement('tr');
        tr.onclick = () => openDetails(rec);

        const revNum = parseFloat(rec.ui_revenue);
        const revenueFormatted = !isNaN(revNum) && revNum > 0
            ? `${(revNum / 1_000_000).toFixed(1)} млн ₽`
            : `<span style="color:var(--text-tertiary); font-style:italic;">${rec.ui_revenue_missing ? 'нет данных' : 'н/д'}</span>`;

        tr.innerHTML = `
            <td class="cell-company">
                <div class="c-name">${rec.ui_name}</div>
                <div class="c-inn">ИНН ${rec.ui_inn || '—'}</div>
            </td>
            <td>${rec.ui_region}</td>
            <td class="num">${revenueFormatted}</td>
            <td class="num">${scoreCellHtml(rec.A_score)}</td>
            <td class="num">${scoreCellHtml(rec.B_score)}</td>
            <td class="num">${scoreCellHtml(rec.C_score)}</td>
            <td class="num">${scoreCellHtml(rec.D_score)}</td>
            <td class="num">${scoreCellHtml(rec.E_score)}</td>
            <td class="num"><span class="score-total-cell">${rec.scoring_total}</span></td>
            <td><span class="tag ${segClass(rec.scoring_segment)}">${rec.scoring_segment}</span></td>
            <td><span class="quality-badge ${qualityClass(rec.ui_data_quality_label)}"><span class="dot"></span>${rec.ui_data_quality_label}</span></td>
            <td>${contactDotsHtml(rec)}</td>
            <td>${stopFlagHtml(rec)}</td>
        `;
        tbody.appendChild(tr);
    });
}

// ─── Детальная панель компании ──────────────────────────────────────────

function contactRowHtml(label, contact) {
    if (!contact || !contact.present) {
        return `<div class="contact-row-item"><span class="ci-label">${label}</span><span class="ci-value absent">нет данных</span></div>`;
    }
    const extra = contact.extra > 0 ? `<span class="ci-extra">+${contact.extra}</span>` : '';
    return `<div class="contact-row-item"><span class="ci-label">${label}</span><span class="ci-value">${contact.display}${extra}</span></div>`;
}

function openDetails(rec) {
    document.getElementById('modal-company-name').innerText = rec.ui_name;
    document.getElementById('modal-inn-top').innerText = `ИНН ${rec.ui_inn || '—'}`;
    document.getElementById('modal-total-score').innerText = (rec.scoring_total ?? 0).toFixed(1);

    const badge = document.getElementById('modal-segment-badge');
    badge.className = `tag ${segClass(rec.scoring_segment)}`;
    badge.innerText = rec.scoring_segment;

    // Категории
    const breakdown = document.getElementById('category-breakdown');
    breakdown.innerHTML = Object.entries(CATEGORY_LABELS).map(([id, label]) => {
        const val = rec[`${id}_score`];
        const isZero = val === 0 || val === null || val === undefined;
        const pct = val || 0;
        return `
            <div class="cat-row">
                <div class="cat-info">
                    <span class="cat-name">${id}. ${label}</span>
                    <span class="cat-score ${isZero ? 'zero' : ''}">${val !== null && val !== undefined ? val : 'н/д'} / 100</span>
                </div>
                <div class="progress-bar-bg"><div class="progress-bar-fill ${isZero ? 'zero' : ''}" style="width:${pct}%;"></div></div>
            </div>`;
    }).join('');

    // Контакты
    const contactList = document.getElementById('contact-list');
    contactList.innerHTML = [
        contactRowHtml('Телефон', rec.ui_contact_phone),
        contactRowHtml('Email', rec.ui_contact_email),
        contactRowHtml('Web-сайт', rec.ui_contact_website),
        rec.ui_has_manager
            ? `<div class="contact-row-item"><span class="ci-label">Руководитель</span><span class="ci-value">${rec.ui_manager}${rec.ui_position ? ' <span class="ci-extra">· ' + rec.ui_position + '</span>' : ''}</span></div>`
            : `<div class="contact-row-item"><span class="ci-label">Руководитель</span><span class="ci-value absent">нет данных</span></div>`,
    ].join('');

    // Диагностика
    const diag = document.getElementById('diag-box');
    const qCls = rec.ui_data_quality_label === 'Высокое' ? 'success' : (rec.ui_data_quality_label === 'Среднее' ? 'warn' : 'danger');
    diag.innerHTML = `
        <div class="diag-item"><span class="diag-label">Регион</span><span class="diag-value">${rec.ui_region}</span></div>
        <div class="diag-item"><span class="diag-label">Отрасль (ОКВЭД)</span><span class="diag-value">${rec.ui_industry || '—'}</span></div>
        <div class="diag-item"><span class="diag-label">Налоговый режим</span><span class="diag-value">${rec.ui_tax_regime || '—'}</span></div>
        <div class="diag-item"><span class="diag-label">Выручка в источнике</span><span class="diag-value">${rec.ui_revenue_missing ? '<span class=\"status-pill danger\">Отсутствует</span>' : '<span class=\"status-pill success\">Указана</span>'}</span></div>
        <div class="diag-item"><span class="diag-label">Качество данных</span><span class="diag-value"><span class="status-pill ${qCls}">${rec.ui_data_quality_label} · ${rec.ui_data_quality_pct}%</span></span></div>
        <div class="diag-item"><span class="diag-label">Нужно ли обогащение</span><span class="diag-value">${rec.ui_needs_enrichment ? 'Да' : 'Нет'}</span></div>
        <div class="diag-item"><span class="diag-label">Адрес</span><span class="diag-value" style="max-width:65%; word-break:break-word;">${rec.ui_address || '—'}</span></div>
    `;

    // Стоп-факторы
    const explainBox = document.getElementById('stop-factors-explain-box');
    const stopList = document.getElementById('modal-stop-factors-list');
    stopList.innerHTML = '';
    const cats = rec.ui_stopped_categories || [];
    const explanations = {
        A: 'Выручка ниже порогового значения для данного региона — категория «Финансовое здоровье» обнулена.',
        B: 'Сработал стоп-фактор масштаба (например, отсутствуют сотрудники или запасы равны нулю).',
        C: 'Нецелевая отрасль по ОКВЭД — компания не представляет коммерческого интереса.',
        D: 'Отсутствуют все каналы связи с компанией (телефон, сайт, адрес, email).',
        E: 'Сработал стоп-фактор юридического статуса (риски, связанные с ОКФС/ОКОПФ).',
    };
    if (cats.length) {
        explainBox.style.display = 'block';
        cats.forEach(c => {
            const li = document.createElement('li');
            li.innerHTML = `<strong>${c}. ${CATEGORY_LABELS[c] || ''}:</strong> ${explanations[c] || 'Сработал стоп-фактор категории.'}`;
            stopList.appendChild(li);
        });
        if (rec.A_stop_factor === 0 && rec.ui_revenue_missing) {
            const li = document.createElement('li');
            li.innerHTML = `<strong>Важно:</strong> выручка отсутствует в исходном файле — стоп-фактор мог сработать из-за нехватки данных, а не подтверждённо низкой выручки. Рекомендуется проверить компанию вручную.`;
            stopList.appendChild(li);
        }
    } else {
        explainBox.style.display = 'none';
    }

    document.getElementById('details-modal').classList.add('open');
    document.getElementById('modal-overlay').classList.add('open');
}

function closeDetails() {
    document.getElementById('details-modal').classList.remove('open');
    document.getElementById('modal-overlay').classList.remove('open');
}

// ─── Экспорт ─────────────────────────────────────────────────────────────

async function downloadScoredExcel() {
    if (!originalFile) return;
    const formData = new FormData();
    formData.append('file', originalFile);

    try {
        const res = await fetch('/score', { method: 'POST', body: formData });
        if (res.ok) {
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `scoring_final_${originalFile.name}`;
            a.click();
        } else {
            alert('Не удалось скачать файл.');
        }
    } catch (e) {
        console.error(e);
        alert('Ошибка сети.');
    }
}