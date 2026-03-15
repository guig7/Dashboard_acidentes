// ─── CHART.JS GLOBAL DEFAULTS ────────────────────────────────────────────────
Chart.defaults.color = '#6b7280';
Chart.defaults.font.family = "'Space Mono', monospace";
Chart.defaults.font.size = 11;

const colors = {
    accent:          '#00c8ff',
    accentSecondary: '#0066cc',
    hazard:          '#ff4040',
    warning:         '#FF6B35',
    positive:        '#00FF87',
    gridLines:       'rgba(255, 255, 255, 0.04)',
    tooltipBg:       'rgba(6, 12, 24, 0.95)',
};

let chartEvolucao      = null;
let chartMortos        = null;
let chartHeatmap       = null;
let chartRanking       = null;
let chartCausas        = null;
let map                = null;
let markerClusterGroup = null;

// ─── URL HELPERS ──────────────────────────────────────────────────────────────
function getUrlComFiltros(basePath) {
    const ano = document.getElementById('filter-ano').value;
    const uf  = document.getElementById('filter-uf').value;
    const params = new URLSearchParams();
    if (ano) params.append('ano', ano);
    if (uf)  params.append('uf', uf);
    const qs = params.toString();
    return qs ? `${basePath}?${qs}` : basePath;
}

// ─── LOAD ALL ─────────────────────────────────────────────────────────────────
function carregarTudo() {
    carregarResumo();
    carregarTaxaSeveridade();
    carregarEvolucaoAno();
    carregarMortosAno();
    carregarHeatmapHorarios();
    carregarRankingEstados();
    carregarTopCausas();
    carregarMapa();
}

document.addEventListener('DOMContentLoaded', () => {
    setTimeout(carregarTudo, 120);
    document.getElementById('filter-ano').addEventListener('change', carregarTudo);
    document.getElementById('filter-uf').addEventListener('change', carregarTudo);
});

// ─── FORMATTERS ───────────────────────────────────────────────────────────────
const formatNum = (n) => new Intl.NumberFormat('pt-BR').format(n);

// ─── CHART OPTIONS FACTORY ────────────────────────────────────────────────────
function chartOptions(overrides = {}) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 600, easing: 'easeOutQuart' },
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: colors.tooltipBg,
                titleColor: colors.accent,
                bodyColor: '#e8eaf2',
                borderColor: 'rgba(0, 200, 255, 0.2)',
                borderWidth: 1,
                padding: 12,
                cornerRadius: 8,
                titleFont: { family: "'Syne', sans-serif", size: 12, weight: '700' },
                bodyFont:  { family: "'Space Mono', monospace", size: 12, weight: '700' },
                callbacks: {
                    label: function(ctx) {
                        const val = ctx.parsed.y ?? ctx.parsed.x ?? ctx.parsed;
                        return `  ${ctx.dataset.label}: ${formatNum(val)}`;
                    }
                }
            }
        },
        scales: {
            x: {
                grid: { color: colors.gridLines, drawBorder: false },
                ticks: { font: { family: "'Space Mono', monospace", size: 10 } }
            },
            y: {
                grid: { color: colors.gridLines, drawBorder: false },
                ticks: {
                    font: { family: "'Space Mono', monospace", size: 10 },
                    callback: (v) => v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v
                }
            }
        },
        ...overrides
    };
}

// ─── KPI ──────────────────────────────────────────────────────────────────────
async function carregarTaxaSeveridade() {
    try {
        const res  = await fetch(getUrlComFiltros('/api/taxa_severidade'));
        const data = await res.json();
        if (!Object.keys(data).length) return;

        document.getElementById('kpi_severidade').textContent = data.taxa_atual.toFixed(2) + '%';

        const comp = document.getElementById('kpi_comparativo');
        if (data.taxa_anterior > 0) {
            const up   = data.variacao >= 0;
            comp.textContent       = `${up ? '▲' : '▼'} ${Math.abs(data.variacao).toFixed(2)}%  ${up ? 'Piora vs ano ant.' : 'Melhora vs ano ant.'}`;
            comp.style.color       = up ? colors.hazard : colors.positive;
            comp.style.borderColor = up ? 'rgba(255,64,64,0.3)' : 'rgba(0,255,135,0.3)';
        } else {
            comp.textContent = 'Sem comparativo disponível';
        }
    } catch(e) { console.error('Taxa severidade:', e); }
}

async function carregarResumo() {
    try {
        const res  = await fetch(getUrlComFiltros('/api/stats_gerais'));
        const data = await res.json();
        animateValue('total_acidentes', 0, data.total_acidentes, 1400);
        animateValue('total_mortos',    0, data.total_mortos,    1400);
        animateValue('total_feridos',   0, data.total_feridos,   1400);
    } catch(e) { console.error('Resumo:', e); }
}

// ─── EVOLUÇÃO ACIDENTES ───────────────────────────────────────────────────────
async function carregarEvolucaoAno() {
    try {
        const res  = await fetch(getUrlComFiltros('/api/acidentes_por_ano'));
        const data = await res.json();
        const ctx  = document.getElementById('evolucaoAcidentes').getContext('2d');

        const grad = ctx.createLinearGradient(0, 0, 0, 320);
        grad.addColorStop(0, 'rgba(0, 200, 255, 0.35)');
        grad.addColorStop(1, 'rgba(0, 200, 255, 0.00)');

        if (chartEvolucao) chartEvolucao.destroy();
        chartEvolucao = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [{
                    label: 'Acidentes',
                    data: data.data,
                    borderColor: colors.accent,
                    backgroundColor: grad,
                    borderWidth: 2.5,
                    pointBackgroundColor: '#050810',
                    pointBorderColor: colors.accent,
                    pointBorderWidth: 2,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: chartOptions()
        });
    } catch(e) { console.error('Evolução:', e); }
}

// ─── MORTOS POR ANO ───────────────────────────────────────────────────────────
async function carregarMortosAno() {
    try {
        const res  = await fetch(getUrlComFiltros('/api/mortos_por_ano'));
        const data = await res.json();
        const ctx  = document.getElementById('evolucaoMortos').getContext('2d');

        const grad = ctx.createLinearGradient(0, 0, 0, 300);
        grad.addColorStop(0, 'rgba(255, 64, 64, 0.8)');
        grad.addColorStop(1, 'rgba(255, 64, 64, 0.15)');

        if (chartMortos) chartMortos.destroy();
        chartMortos = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{
                    label: 'Mortos',
                    data: data.data,
                    backgroundColor: grad,
                    borderRadius: 5,
                    barPercentage: 0.55
                }]
            },
            options: chartOptions()
        });
    } catch(e) { console.error('Mortos:', e); }
}

// ─── HEATMAP HORÁRIOS ─────────────────────────────────────────────────────────
async function carregarHeatmapHorarios() {
    try {
        const res  = await fetch(getUrlComFiltros('/api/heatmap_horarios'));
        const data = await res.json();
        if (!data.labels) return;

        const canvas = document.getElementById('heatmapHorarios');
        if (!canvas) return;
        if (chartHeatmap) chartHeatmap.destroy();

        chartHeatmap = new Chart(canvas.getContext('2d'), {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [
                    {
                        label: 'Acidentes',
                        data: data.acidentes,
                        backgroundColor: 'rgba(0, 200, 255, 0.45)',
                        borderColor: 'rgba(0, 200, 255, 0.7)',
                        borderWidth: 1,
                        borderRadius: 3,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Severidade (%)',
                        data: data.severidade,
                        type: 'line',
                        borderColor: colors.hazard,
                        backgroundColor: 'transparent',
                        borderWidth: 2.5,
                        pointBackgroundColor: colors.hazard,
                        pointBorderColor: '#050810',
                        pointBorderWidth: 2,
                        pointRadius: 3,
                        yAxisID: 'y1',
                        tension: 0.4,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 600 },
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        display: true,
                        labels: { font: { family: "'Space Mono', monospace", size: 9 }, color: '#6b7280', boxWidth: 10, padding: 16 }
                    },
                    tooltip: {
                        backgroundColor: colors.tooltipBg,
                        titleColor: colors.accent,
                        bodyColor: '#e8eaf2',
                        borderColor: 'rgba(0,200,255,0.2)',
                        borderWidth: 1,
                        padding: 12,
                        cornerRadius: 8
                    }
                },
                scales: {
                    y:  { type: 'linear', position: 'left',  grid: { color: colors.gridLines }, ticks: { color: colors.accent,  font: { size: 9 }, callback: v => v >= 1000 ? v/1000+'k' : v } },
                    y1: { type: 'linear', position: 'right', grid: { drawOnChartArea: false },  ticks: { color: colors.hazard,  font: { size: 9 }, callback: v => v + '%' } },
                    x:  { grid: { color: colors.gridLines }, ticks: { font: { size: 9 } } }
                }
            }
        });
    } catch(e) { console.error('Heatmap:', e); }
}

// ─── RANKING ESTADOS ──────────────────────────────────────────────────────────
async function carregarRankingEstados() {
    try {
        const res  = await fetch(getUrlComFiltros('/api/ranking_estados'));
        const data = await res.json();
        if (!data.labels?.length) return;

        const bgColors     = data.taxa_severidade.map(t => t > 15 ? 'rgba(255,64,64,0.7)' : t > 12 ? 'rgba(255,107,53,0.65)' : 'rgba(0,200,255,0.55)');
        const borderColors = data.taxa_severidade.map(t => t > 15 ? colors.hazard : t > 12 ? colors.warning : colors.accent);

        if (chartRanking) chartRanking.destroy();
        chartRanking = new Chart(document.getElementById('rankingEstados').getContext('2d'), {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{ label: 'Taxa Severidade (%)', data: data.taxa_severidade, backgroundColor: bgColors, borderColor: borderColors, borderWidth: 1, borderRadius: 5 }]
            },
            options: {
                ...chartOptions({ indexAxis: 'y' }),
                scales: {
                    x: { beginAtZero: true, max: 25, grid: { color: colors.gridLines }, ticks: { font: { family: "'Space Mono', monospace", size: 10 }, callback: v => v + '%' } },
                    y: { grid: { color: colors.gridLines }, ticks: { font: { family: "'Space Mono', monospace", size: 10 } } }
                }
            }
        });
    } catch(e) { console.error('Ranking:', e); }
}

// ─── TOP CAUSAS ───────────────────────────────────────────────────────────────
async function carregarTopCausas() {
    try {
        const res  = await fetch(getUrlComFiltros('/api/causas'));
        const data = await res.json();
        if (!data.labels?.length) return;

        // Cores baseadas em severidade
        const bgColors = data.taxa_severidade.map(t =>
            t > 5  ? 'rgba(255, 64, 64, 0.65)'   :
            t > 3  ? 'rgba(255, 107, 53, 0.65)'   :
                     'rgba(0, 200, 255, 0.55)'
        );
        const borderColors = data.taxa_severidade.map(t =>
            t > 5  ? colors.hazard  :
            t > 3  ? colors.warning :
                     colors.accent
        );

        // Encurta labels longos para o gráfico
        const labelsShort = data.labels.map(l => l.length > 35 ? l.slice(0, 33) + '…' : l);

        if (chartCausas) chartCausas.destroy();
        chartCausas = new Chart(document.getElementById('topCausas').getContext('2d'), {
            type: 'bar',
            data: {
                labels: labelsShort,
                datasets: [{
                    label: 'Acidentes',
                    data: data.data,
                    backgroundColor: bgColors,
                    borderColor: borderColors,
                    borderWidth: 1,
                    borderRadius: 5
                }]
            },
            options: {
                ...chartOptions({ indexAxis: 'y' }),
                scales: {
                    x: {
                        beginAtZero: true,
                        grid: { color: colors.gridLines },
                        ticks: { font: { family: "'Space Mono', monospace", size: 10 }, callback: v => v >= 1000 ? (v/1000).toFixed(0)+'k' : v }
                    },
                    y: {
                        grid: { color: colors.gridLines },
                        ticks: { font: { family: "'Space Mono', monospace", size: 9 } }
                    }
                }
            }
        });

        // Preenche a tabela lateral
        const tbody = document.getElementById('causasTabelaBody');
        tbody.innerHTML = data.labels.map((causa, i) => {
            const sev    = data.taxa_severidade[i];
            const cor    = sev > 5 ? colors.hazard : sev > 3 ? colors.warning : colors.accent;
            const label  = causa.length > 40 ? causa.slice(0, 38) + '…' : causa;
            return `
                <div class="causas-tabela-row">
                    <span class="causa-nome" title="${causa}">${label}</span>
                    <span>${formatNum(data.data[i])}</span>
                    <span style="color: ${colors.hazard}">${formatNum(data.mortos[i])}</span>
                    <span style="color: ${cor}; font-weight: 700">${sev.toFixed(1)}%</span>
                </div>
            `;
        }).join('');

    } catch(e) { console.error('Top causas:', e); }
}

// ─── MAPA COM POPUP ───────────────────────────────────────────────────────────
async function carregarMapa() {
    try {
        const res         = await fetch(getUrlComFiltros('/api/mapa'));
        const registros   = await res.json();

        if (!map) {
            map = L.map('mapContainer', { zoomControl: true, attributionControl: true })
                   .setView([-14.2, -51.9], 4);

            L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
                attribution: '© OpenStreetMap © CARTO',
                maxZoom: 19,
                opacity: 0.9
            }).addTo(map);

            markerClusterGroup = L.markerClusterGroup({
                maxClusterRadius: 80,
                iconCreateFunction: function(cluster) {
                    const count = cluster.getChildCount();
                    const color = count > 100 ? '#ff4040' : count > 50 ? '#FF6B35' : '#00c8ff';
                    const size  = count > 100 ? 44 : count > 50 ? 38 : 32;
                    return new L.DivIcon({
                        html: `<div style="
                            background:${color};border-radius:50%;
                            width:${size}px;height:${size}px;
                            display:flex;align-items:center;justify-content:center;
                            font-family:'Space Mono',monospace;font-size:11px;font-weight:700;
                            color:#050810;box-shadow:0 0 12px ${color}88;
                        ">${count}</div>`,
                        iconSize: [size, size]
                    });
                }
            });
            map.addLayer(markerClusterGroup);
            window.addEventListener('resize', () => map && map.invalidateSize());
        } else {
            markerClusterGroup.clearLayers();
        }

        const dotIcon = L.divIcon({
            html: `<div style="width:8px;height:8px;background:#00c8ff;border-radius:50%;box-shadow:0 0 6px #00c8ff88;"></div>`,
            iconSize: [8, 8], iconAnchor: [4, 4], className: ''
        });

        const popupStyle = `
            font-family:'Space Mono',monospace;
            background:#060d1a;
            color:#e8eaf2;
            border:1px solid rgba(0,200,255,0.2);
            border-radius:10px;
            padding:0;
            min-width:220px;
        `;

        const markers = registros.map(r => {
            const mortosCor  = r.mortos > 0  ? '#ff4040' : '#6b7280';
            const feridosCor = r.feridos > 0 ? '#FF6B35' : '#6b7280';

            const popup = L.popup({ maxWidth: 280, className: 'custom-popup' }).setContent(`
                <div style="${popupStyle}">
                    <div style="background:rgba(0,200,255,0.08);padding:10px 14px;border-bottom:1px solid rgba(0,200,255,0.1);border-radius:10px 10px 0 0;">
                        <div style="font-size:0.7rem;color:#6b7280;letter-spacing:1px;text-transform:uppercase;">Município</div>
                        <div style="font-size:0.95rem;font-weight:700;color:#e8eaf2;margin-top:2px;">${r.municipio} / ${r.uf}</div>
                    </div>
                    <div style="padding:10px 14px;display:flex;flex-direction:column;gap:6px;">
                        <div style="font-size:0.68rem;color:#6b7280;">
                            <span style="color:#a0a0b0;">📅</span> ${r.data} às ${r.horario || '—'}
                        </div>
                        <div style="font-size:0.7rem;color:#a0a0b0;line-height:1.4;">
                            <span style="color:#6b7280;">Causa:</span><br>
                            <span style="color:#e8eaf2;">${r.causa_acidente}</span>
                        </div>
                        <div style="font-size:0.68rem;color:#a0a0b0;">
                            <span style="color:#6b7280;">Classificação:</span>
                            <span style="color:#e8eaf2;">${r.classificacao_acidente}</span>
                        </div>
                        <div style="display:flex;gap:12px;margin-top:4px;">
                            <div style="font-size:0.75rem;font-weight:700;color:${mortosCor};">
                                ☠ ${r.mortos} morto${r.mortos !== 1 ? 's' : ''}
                            </div>
                            <div style="font-size:0.75rem;font-weight:700;color:${feridosCor};">
                                🤕 ${r.feridos} ferido${r.feridos !== 1 ? 's' : ''}
                            </div>
                        </div>
                    </div>
                </div>
            `);

            return L.marker([r.latitude, r.longitude], { icon: dotIcon }).bindPopup(popup);
        });

        markerClusterGroup.addLayers(markers);

        if (markerClusterGroup.getLayers().length > 0) {
            map.fitBounds(new L.featureGroup(markerClusterGroup.getLayers()).getBounds(), { padding: [40, 40] });
        }
    } catch(e) { console.error('Mapa:', e); }
}

// ─── ANIMATE VALUE ────────────────────────────────────────────────────────────
function animateValue(id, start, end, duration) {
    const obj = document.getElementById(id);
    if (!obj || start === end) return;
    const stepAmount = Math.ceil(Math.abs(end - start) / (duration / 16));
    let current = start;
    const timer = setInterval(() => {
        current += stepAmount;
        if (current >= end) { current = end; clearInterval(timer); }
        obj.innerHTML = formatNum(current);
    }, 16);
}
