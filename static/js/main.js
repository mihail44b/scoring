let currentTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', currentTheme);
        updateThemeButtonUI();

        let dashboardData = null;
        let originalFile = null;
        let categoryChartInstance = null;
        let segmentsChartInstance = null;

        function toggleTheme() {
            currentTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', currentTheme);
            localStorage.setItem('theme', currentTheme);
            updateThemeButtonUI();
            if (dashboardData) {
                renderCharts(dashboardData.stats);
            }
        }

        function updateThemeButtonUI() {
            const btn = document.getElementById('themeToggleBtn');
            if (currentTheme === 'light') {
                btn.innerHTML = '🌙 Тёмная тема';
            } else {
                btn.innerHTML = '☀️ Светлая тема';
            }
        }

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
                const res = await fetch('/api/score/full', {
                    method: 'POST',
                    body: formData
                });

                if (res.ok) {
                    const data = await res.json();
                    dashboardData = data;

                    // Hide upload card, show dashboard
                    document.getElementById('upload-panel').style.display = 'none';
                    document.getElementById('dashboard').style.display = 'flex';

                    // Update header file info
                    const fileDisplay = document.getElementById('file-name-display');
                    fileDisplay.innerText = `Файл: ${file.name}`;
                    fileDisplay.style.display = 'inline';

                    // Process UI details
                    populateKPIs(data.stats);
                    renderCharts(data.stats);
                    populateTable(data.records);
                } else {
                    const err = await res.json();
                    status.innerText = `Ошибка расчета: ${err.detail || 'Неизвестная ошибка'}`;
                }
            } catch (e) {
                console.error(e);
                status.innerText = 'Сетевая ошибка при отправке файла.';
            } finally {
                spinner.style.display = 'none';
            }
        }

        function populateKPIs(stats) {
            document.getElementById('kpi-total').innerText = stats.total;
            document.getElementById('kpi-hot').innerText = stats.segments.Горячий || 0;
            document.getElementById('kpi-warm-cold').innerText = `${stats.segments.Тёплый || 0} / ${stats.segments.Холодный || 0}`;
            document.getElementById('kpi-avg').innerText = stats.averages.total.toFixed(1);

            document.getElementById('kpi-chuvash').innerText = stats.chuvasia_count;

            const totalStops = stats.stops.revenue_stop + stats.stops.industry_stop;
            document.getElementById('kpi-stops').innerText = totalStops;
            document.getElementById('stop-a-count').innerText = stats.stops.revenue_stop;
            document.getElementById('stop-c-count').innerText = stats.stops.industry_stop;
        }

        function renderCharts(stats) {
            const isDark = currentTheme === 'dark';
            const textColor = isDark ? '#f8fafc' : '#1e293b';
            const gridColor = isDark ? '#334155' : '#e2e8f0';

            // 1. Categories Average Chart
            if (categoryChartInstance) categoryChartInstance.destroy();
            const ctxCat = document.getElementById('categoryChart').getContext('2d');
            categoryChartInstance = new Chart(ctxCat, {
                type: 'bar',
                data: {
                    labels: ['А Фин. здоровье', 'B Масштаб', 'C Отрасль', 'D Контакты', 'E Юр. статус'],
                    datasets: [{
                        label: 'Средний балл категории (0-100)',
                        data: [
                            stats.averages.A,
                            stats.averages.B,
                            stats.averages.C,
                            stats.averages.D,
                            stats.averages.E
                        ],
                        backgroundColor: [
                            'rgba(59, 130, 246, 0.85)',
                            'rgba(99, 102, 241, 0.85)',
                            'rgba(16, 185, 129, 0.85)',
                            'rgba(245, 158, 11, 0.85)',
                            'rgba(139, 92, 246, 0.85)'
                        ],
                        borderColor: isDark ? '#1e293b' : '#ffffff',
                        borderWidth: 2,
                        borderRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: { padding: 12 }
                    },
                    scales: {
                        y: {
                            min: 0,
                            max: 100,
                            grid: { color: gridColor },
                            ticks: { color: textColor }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: textColor }
                        }
                    }
                }
            });

            // 2. Segment Donut Chart
            if (segmentsChartInstance) segmentsChartInstance.destroy();
            const ctxSeg = document.getElementById('segmentsChart').getContext('2d');
            segmentsChartInstance = new Chart(ctxSeg, {
                type: 'doughnut',
                data: {
                    labels: ['Горячие', 'Тёплые', 'Холодные'],
                    datasets: [{
                        data: [
                            stats.segments.Горячий || 0,
                            stats.segments.Тёплый || 0,
                            stats.segments.Холодный || 0
                        ],
                        backgroundColor: [
                            '#ef4444', // Hot (Red)
                            '#f59e0b', // Warm (Orange)
                            '#10b981'  // Cold (Green)
                        ],
                        borderColor: isDark ? '#1e293b' : '#ffffff',
                        borderWidth: 3
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '65%',
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                color: textColor,
                                font: { family: 'Inter', weight: 500, size: 12 },
                                padding: 16
                            }
                        },
                        tooltip: { padding: 12 }
                    }
                }
            });
        }

        function populateTable(records) {
            const tbody = document.getElementById('table-body');
            tbody.innerHTML = '';

            if (records.length === 0) {
                tbody.innerHTML = `<tr><td colspan="10" class="empty-state">Нет данных, соответствующих выбранным фильтрам</td></tr>`;
                return;
            }

            records.forEach(rec => {
                const tr = document.createElement('tr');
                tr.onclick = () => openDetails(rec);

                // Segment cell class
                let segClass = 'cold';
                if (rec.scoring_segment === 'Горячий') segClass = 'hot';
                else if (rec.scoring_segment === 'Тёплый') segClass = 'warm';

                // Chuvasia badges selector
                const isChuvash = rec.A_region_coeff > 1.0;
                const chuvashBadge = isChuvash ? `<span class="tag badge chuvash" style="font-size:10px;">Чувашия х3</span>` : '';



                // Formatted Revenue
                const revNum = parseFloat(rec.ui_revenue);
                const revenueFormatted = !isNaN(revNum) && revNum > 0
                    ? `${(revNum / 1_000_000).toFixed(1)} млн ₽`
                    : '<span style="color:var(--text-secondary); font-style:italic;">н/д</span>';

                tr.innerHTML = `
                    <td>
                        <div style="font-weight:600;">${rec.ui_name}</div>
                        <div style="font-size:12px; color:var(--text-secondary); max-width: 320px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                            ${rec.ui_address}
                        </div>
                    </td>
                    <td>${rec.ui_inn || '-'}</td>
                    <td>${revenueFormatted}</td>
                    <td style="font-weight:600;">${rec.A_score !== null ? rec.A_score : '-'}</td>
                    <td>${rec.B_score !== null ? rec.B_score : '-'}</td>
                    <td>${rec.C_score !== null ? rec.C_score : '-'}</td>
                    <td style="font-weight:700; color:var(--primary-light);">${rec.scoring_total}</td>
                    <td><span class="tag ${segClass}">${rec.scoring_segment}</span></td>

                    <td>${chuvashBadge || '<span style="color:var(--text-secondary); font-size:11px;">РФ</span>'}</td>
                `;
                tbody.appendChild(tr);
            });
        }

        function applyFilters() {
            if (!dashboardData) return;

            const searchQuery = document.getElementById('searchInput').value.toLowerCase().trim();
            const segmentFilter = document.getElementById('segmentFilter').value;

            const regionFilter = document.getElementById('regionFilter').value;

            const filtered = dashboardData.records.filter(rec => {
                // Search query filter
                const nameMatch = String(rec.ui_name).toLowerCase().includes(searchQuery);
                const innMatch = String(rec.ui_inn).toLowerCase().includes(searchQuery);
                if (searchQuery && !nameMatch && !innMatch) return false;

                // Segment filter
                if (segmentFilter && rec.scoring_segment !== segmentFilter) return false;



                // Region filter
                if (regionFilter) {
                    const isChuvash = rec.A_region_coeff > 1.0;
                    if (regionFilter === 'chuvash' && !isChuvash) return false;
                    if (regionFilter === 'other' && isChuvash) return false;
                }

                return true;
            });

            populateTable(filtered);
        }

        function openDetails(rec) {
            document.getElementById('modal-company-name').innerText = rec.ui_name;
            document.getElementById('modal-total-score').innerText = rec.scoring_total.toFixed(1);

            // Score circle
            const circle = document.getElementById('details-score-circle');
            circle.style.setProperty('--score-pct', rec.scoring_total);

            // Segment badge
            const badge = document.getElementById('modal-segment-badge');
            badge.className = 'tag';
            let segClass = 'cold';
            if (rec.scoring_segment === 'Горячий') segClass = 'hot';
            else if (rec.scoring_segment === 'Тёплый') segClass = 'warm';
            badge.classList.add(segClass);
            badge.innerText = rec.scoring_segment;

            // Categories
            const setCat = (catId, val) => {
                document.getElementById(`modal-score-${catId}`).innerText = val !== null ? `${val} / 100` : 'н/д';
                document.getElementById(`modal-bar-${catId}`).style.width = val !== null ? `${val}%` : '0%';
            };
            setCat('a', rec.A_score);
            setCat('b', rec.B_score);
            setCat('c', rec.C_score);
            setCat('d', rec.D_score);
            setCat('e', rec.E_score);

            // Diags
            document.getElementById('modal-inn').innerText = rec.ui_inn || 'Не указан';
            document.getElementById('modal-address').innerText = rec.ui_address || 'Не указан';

            const isChuvash = rec.A_region_coeff > 1.0;
            document.getElementById('modal-region-coeff').innerHTML = isChuvash
                ? `<span style="color:#4f46e5; font-weight:700;">Чувашская Республика (х3.0 пониженный финансовый порог)</span>`
                : 'Обычный регион (Москва)';



            // Financial missing explanation
            const hasFin = !rec.A_no_revenue_data;
            document.getElementById('modal-fin-exists').innerHTML = hasFin
                ? '<span class="status-pill success">Доступны</span>'
                : '<span class="status-pill danger">Финансовые показатели отсутствуют в файле</span>';

            document.getElementById('modal-status-c').innerHTML = rec.C_status === 'ок'
                ? '<span class="status-pill success">ок</span>'
                : `<span class="status-pill danger">${rec.C_status}</span>`;

            // Stop-factors check
            const stopList = document.getElementById('modal-stop-factors-list');
            const explainBox = document.getElementById('stop-factors-explain-box');
            stopList.innerHTML = '';
            let hasStops = false;

            if (rec.A_stop_factor === 0 && !rec.A_no_revenue_data) {
                hasStops = true;
                const li = document.createElement('li');
                li.innerHTML = `<strong>Выручка ниже порогового значения:</strong> фактическая выручка меньше действующего порога равного <strong>${(540 / 3).toFixed(0)} - 360 млн. ₽</strong>`;
                stopList.appendChild(li);
            }

            if (rec.C_stop_factor === 0) {
                hasStops = true;
                const li = document.createElement('li');
                li.innerHTML = `<strong>Нецелевой сектор (ОКВЭД Тир 4):</strong> Указанный ОКВЭД относится к компаниям не представляющим коммерческого интереса`;
                stopList.appendChild(li);
            }

            if (hasStops) {
                explainBox.style.display = 'block';
            } else {
                explainBox.style.display = 'none';
            }

            // Open sidepanel
            document.getElementById('details-modal').classList.add('open');
            document.getElementById('modal-overlay').classList.add('open');
        }

        function closeDetails() {
            document.getElementById('details-modal').classList.remove('open');
            document.getElementById('modal-overlay').classList.remove('open');
        }

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