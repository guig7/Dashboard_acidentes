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
let accidentPointsLayer = null;
let accidentPointsRenderer = null;
let accidentHeatLayer = null;
let accidentMode = 'points';
let roadLayer           = null;
let roadGlowLayer       = null;
let countryLayer        = null;
let stateLayer           = null;
let roadGeometries      = new Map();
let roadAccidents       = new Map();
let availableRoads      = new Set();
let mapLoadSequence     = 0;
let filterReloadTimer   = null;
let renderedMapFilterState = null;
let analystEnabled = false;
let distributionPage = 1;
let distributionLoadSequence = 0;
let recordsPage = 1;
let recordsLoadSequence = 0;
const RECORD_FIELD_LABELS = {
    id: 'ID',
    data_inversa: 'Data',
    dia_semana: 'Dia da semana',
    horario: 'Horário',
    uf: 'UF',
    br: 'BR',
    km: 'Quilômetro',
    municipio: 'Município',
    causa_acidente: 'Causa registrada',
    tipo_acidente: 'Tipo de acidente',
    classificacao_acidente: 'Classificação do acidente',
    fase_dia: 'Fase do dia',
    sentido_via: 'Sentido da via',
    condicao_metereologica: 'Condição meteorológica',
    tipo_pista: 'Tipo de pista',
    tracado_via: 'Traçado da via',
    uso_solo: 'Uso do solo',
    pessoas: 'Pessoas',
    mortos: 'Mortos',
    feridos_leves: 'Feridos leves',
    feridos_graves: 'Feridos graves',
    ilesos: 'Ilesos',
    ignorados: 'Ignorados',
    feridos: 'Feridos',
    veiculos: 'Veículos',
    latitude: 'Latitude',
    longitude: 'Longitude',
    regional: 'Regional',
    delegacia: 'Delegacia',
    uop: 'Unidade operacional'
};
const UF_IBGE_CODES = {
    AC: '12', AL: '27', AP: '16', AM: '13', BA: '29', CE: '23', DF: '53', ES: '32', GO: '52',
    MA: '21', MT: '51', MS: '50', MG: '31', PA: '15', PB: '25', PR: '41', PE: '26', PI: '22',
    RJ: '33', RN: '24', RS: '43', RO: '11', RR: '14', SC: '42', SP: '35', SE: '28', TO: '17'
};

// ─── URL HELPERS ──────────────────────────────────────────────────────────────
function getUrlComFiltros(basePath, filters = null) {
    const ano = filters?.ano ?? document.getElementById('filter-ano').value;
    const uf  = filters?.uf ?? document.getElementById('filter-uf').value;
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
    carregarDistribuicao();
    carregarRegistros();
    carregarMapa();
}

function agendarAtualizacaoFiltros() {
    clearTimeout(filterReloadTimer);
    filterReloadTimer = setTimeout(carregarTudo, 180);
}

document.addEventListener('DOMContentLoaded', () => {
    setTimeout(carregarTudo, 120);
    document.getElementById('filter-ano').addEventListener('change', agendarAtualizacaoFiltros);
    document.getElementById('filter-uf').addEventListener('change', agendarAtualizacaoFiltros);
    document.getElementById('distribution-dimension').addEventListener('change', () => carregarDistribuicao());
    document.getElementById('distribution-metric').addEventListener('change', () => carregarDistribuicao());
    document.getElementById('distribution-previous').addEventListener('click', () => {
        if (distributionPage > 1) {
            distributionPage -= 1;
            carregarDistribuicao(false);
        }
    });
    document.getElementById('distribution-next').addEventListener('click', () => {
        distributionPage += 1;
        carregarDistribuicao(false);
    });
    document.getElementById('records-previous').addEventListener('click', () => {
        if (recordsPage > 1) {
            recordsPage -= 1;
            carregarRegistros(false);
        }
    });
    document.getElementById('records-next').addEventListener('click', () => {
        recordsPage += 1;
        carregarRegistros(false);
    });
    document.getElementById('filter-br').addEventListener('change', carregarMapa);
    document.querySelectorAll('[data-map-mode]').forEach(button => {
        button.addEventListener('click', () => setAccidentMode(button.dataset.mapMode));
    });
    carregarListaRodovias();
    carregarStatusAnalista();
});

// ─── FORMATTERS ───────────────────────────────────────────────────────────────
const formatNum = (n) => new Intl.NumberFormat('pt-BR').format(n);

function formatRecordValue(value) {
    return value === null || value === undefined || value === '' ? '—' : String(value);
}

function appendCell(row, value, className = '') {
    const cell = document.createElement('td');
    cell.textContent = formatRecordValue(value);
    if (className) cell.className = className;
    row.appendChild(cell);
    return cell;
}

async function carregarDistribuicao(resetPage = true) {
    if (resetPage) distributionPage = 1;
    const sequence = ++distributionLoadSequence;
    const status = document.getElementById('distribution-status');
    const tbody = document.getElementById('distribution-table-body');
    const previous = document.getElementById('distribution-previous');
    const next = document.getElementById('distribution-next');
    const pageStatus = document.getElementById('distribution-page-status');
    const dimension = document.getElementById('distribution-dimension').value;
    const metric = document.getElementById('distribution-metric').value;
    status.textContent = 'Consultando a distribuição...';
    status.dataset.state = 'loading';
    tbody.innerHTML = '';
    previous.disabled = true;
    next.disabled = true;
    pageStatus.textContent = '';

    try {
        const url = new URL(getUrlComFiltros('/api/distribuicao'), window.location.origin);
        url.searchParams.set('dimensao', dimension);
        url.searchParams.set('metrica', metric);
        url.searchParams.set('pagina', String(distributionPage));
        url.searchParams.set('por_pagina', '25');
        const response = await fetch(url);
        const payload = await response.json().catch(() => null);
        if (!response.ok) {
            throw new Error(payload && typeof payload.erro === 'string'
                ? payload.erro : 'Não foi possível carregar a distribuição.');
        }
        if (!payload || !Array.isArray(payload.resultado) || !Number.isInteger(payload.total_paginas)) {
            throw new Error('A API retornou uma distribuição inválida.');
        }
        if (sequence !== distributionLoadSequence) return;

        payload.resultado.forEach(item => {
            const row = document.createElement('tr');
            appendCell(row, item.valor, 'category-cell');
            ['acidentes', 'mortes', 'feridos', 'feridos_leves', 'feridos_graves',
                'pessoas', 'ilesos', 'ignorados', 'veiculos'].forEach(field => {
                appendCell(row, item[field]);
            });
            tbody.appendChild(row);
        });

        const totalPages = payload.total_paginas;
        status.textContent = `${formatNum(payload.total_categorias)} categorias · ${formatNum(payload.total_registros)} registros no recorte.`;
        status.dataset.state = 'ready';
        pageStatus.textContent = totalPages
            ? `Página ${formatNum(payload.pagina)} de ${formatNum(totalPages)}`
            : 'Nenhuma categoria disponível';
        previous.disabled = payload.pagina <= 1;
        next.disabled = payload.pagina >= totalPages;
    } catch (error) {
        if (sequence !== distributionLoadSequence) return;
        console.error('Distribuição dos dados:', error);
        status.textContent = error.message || 'Não foi possível carregar a distribuição.';
        status.dataset.state = 'error';
    }
}

async function carregarRegistros(resetPage = true) {
    if (resetPage) recordsPage = 1;
    const sequence = ++recordsLoadSequence;
    const status = document.getElementById('records-status');
    const tbody = document.getElementById('records-table-body');
    const previous = document.getElementById('records-previous');
    const next = document.getElementById('records-next');
    const pageStatus = document.getElementById('records-page-status');
    status.textContent = 'Consultando os registros...';
    status.dataset.state = 'loading';
    tbody.innerHTML = '';
    previous.disabled = true;
    next.disabled = true;
    pageStatus.textContent = '';

    try {
        const url = new URL(getUrlComFiltros('/api/registros'), window.location.origin);
        url.searchParams.set('pagina', String(recordsPage));
        url.searchParams.set('por_pagina', '50');
        const response = await fetch(url);
        const payload = await response.json().catch(() => null);
        if (!response.ok) {
            throw new Error(payload && typeof payload.erro === 'string'
                ? payload.erro : 'Não foi possível carregar os registros.');
        }
        if (!payload || !Array.isArray(payload.registros) || !Number.isInteger(payload.total_paginas)) {
            throw new Error('A API retornou registros em formato inválido.');
        }
        if (sequence !== recordsLoadSequence) return;

        const visibleFields = [
            'data_inversa', 'horario', 'uf', 'br', 'municipio',
            'condicao_metereologica', 'causa_acidente', 'tipo_acidente',
            'classificacao_acidente', 'mortos', 'feridos'
        ];
        payload.registros.forEach(record => {
            const row = document.createElement('tr');
            visibleFields.forEach(field => appendCell(row, record[field]));

            const detailsCell = document.createElement('td');
            const details = document.createElement('details');
            const summary = document.createElement('summary');
            summary.textContent = 'Todos os campos';
            const fields = document.createElement('dl');
            fields.className = 'record-fields';
            Object.entries(record).forEach(([field, value]) => {
                const label = document.createElement('dt');
                label.textContent = RECORD_FIELD_LABELS[field] || field;
                const content = document.createElement('dd');
                content.textContent = formatRecordValue(value);
                fields.append(label, content);
            });
            details.append(summary, fields);
            detailsCell.appendChild(details);
            row.appendChild(detailsCell);
            tbody.appendChild(row);
        });

        const totalPages = payload.total_paginas;
        status.textContent = `${formatNum(payload.registros.length)} registros nesta página · ${formatNum(payload.total_registros)} no recorte.`;
        status.dataset.state = 'ready';
        pageStatus.textContent = totalPages
            ? `Página ${formatNum(payload.pagina)} de ${formatNum(totalPages)}`
            : 'Nenhum registro disponível';
        previous.disabled = payload.pagina <= 1;
        next.disabled = payload.pagina >= totalPages;
    } catch (error) {
        if (sequence !== recordsLoadSequence) return;
        console.error('Registros completos:', error);
        status.textContent = error.message || 'Não foi possível carregar os registros.';
        status.dataset.state = 'error';
    }
}

async function carregarStatusAnalista() {
    const form = document.getElementById('analyst-form');
    const question = document.getElementById('analyst-question');
    const submit = document.getElementById('analyst-submit');
    const status = document.getElementById('analyst-status');
    const charCount = document.getElementById('analyst-char-count');
    if (!form || !question || !submit || !status || !charCount) return;

    question.addEventListener('input', () => {
        charCount.textContent = `${question.value.length}/500`;
    });
    form.addEventListener('submit', enviarPerguntaAnalista);

    try {
        const response = await fetch('/api/analista/status');
        const payload = await response.json();
        if (!response.ok || typeof payload.habilitado !== 'boolean') {
            throw new Error('Resposta inválida ao verificar a disponibilidade.');
        }
        if (!payload.habilitado) {
            status.textContent = 'Recurso experimental desativado no momento.';
            status.dataset.state = 'disabled';
            return;
        }

        analystEnabled = true;
        question.disabled = false;
        submit.disabled = false;
        status.textContent = 'Disponível. As respostas usam somente consultas verificáveis do painel.';
        status.dataset.state = 'ready';
    } catch (error) {
        console.error('Falha ao verificar o analista de dados:', error);
        status.textContent = 'Não foi possível verificar a disponibilidade do analista.';
        status.dataset.state = 'error';
    }
}

async function enviarPerguntaAnalista(event) {
    event.preventDefault();
    const question = document.getElementById('analyst-question');
    const submit = document.getElementById('analyst-submit');
    const status = document.getElementById('analyst-status');
    const answer = document.getElementById('analyst-answer');
    const resultData = document.getElementById('analyst-result-data');
    const responseContainer = document.getElementById('analyst-response');
    if (!analystEnabled || !question || !submit || !status || !answer || !resultData || !responseContainer) return;

    const pergunta = question.value.trim();
    if (!pergunta) return;

    submit.disabled = true;
    question.disabled = true;
    responseContainer.hidden = true;
    status.textContent = 'Analisando a pergunta e consultando os dados...';
    status.dataset.state = 'loading';

    try {
        const response = await fetch('/api/analista/perguntar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pergunta }),
        });
        const payload = await response.json().catch(() => null);
        if (!response.ok) {
            throw new Error(
                payload && typeof payload.erro === 'string'
                    ? payload.erro
                    : 'Não foi possível concluir a consulta.'
            );
        }
        if (!payload || typeof payload.resposta !== 'string' || typeof payload.fonte !== 'string') {
            throw new Error('A API retornou uma resposta inválida.');
        }

        answer.textContent = payload.resposta;
        const evidence = Array.isArray(payload.consultas)
            ? { consultas: payload.consultas, fonte: payload.fonte }
            : { consulta: payload.consulta, resultado: payload.resultado, fonte: payload.fonte };
        resultData.textContent = JSON.stringify(evidence, null, 2);
        responseContainer.hidden = false;
        status.textContent = 'Análise concluída. Confira as consultas, os dados e a fonte abaixo.';
        status.dataset.state = 'ready';
    } catch (error) {
        console.error('Falha ao consultar o analista de dados:', error);
        status.textContent = error.message || 'Não foi possível concluir a consulta.';
        status.dataset.state = 'error';
    } finally {
        question.disabled = false;
        submit.disabled = false;
    }
}

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
                datasets: [{
                    label: 'Taxa Severidade (%)',
                    data: data.taxa_severidade,
                    backgroundColor: bgColors,
                    borderColor: borderColors,
                    borderWidth: 1,
                    borderRadius: 5
                    }]
            },
            options: {
                ...chartOptions({ indexAxis: 'y', maintainAspectRatio: false }),
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: function(ctx) {
                                return `  Taxa Severidade: ${ctx.parsed.x.toFixed(2)}%`;
                            }
                        }
                    }
                },
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

        const tbody = document.getElementById('causasTabelaBody');
        tbody.innerHTML = data.labels.map((causa, i) => {
            const sev = data.taxa_severidade[i];
            const cor = sev > 5 ? colors.hazard : sev > 3 ? colors.warning : colors.accent;
            return `
                <div class="causas-tabela-row">
                    <span class="causa-nome" title="${causa}">${causa}</span>
                    <span>${formatNum(data.data[i])}</span>
                    <span style="color: ${colors.hazard}">${formatNum(data.mortos[i])}</span>
                    <span style="color: ${cor}; font-weight: 700">${sev.toFixed(1)}%</span>
                </div>
            `;
        }).join('');

    } catch(e) { console.error('Top causas:', e); }
}

// ─── MAPA COM TRAJETOS OFICIAIS E ACIDENTES ──────────────────────────────────
async function carregarListaRodovias() {
    try {
        const [manifestResponse, accidentsResponse] = await Promise.all([
            fetch('/data/roads/manifest.json'),
            fetch('/data/roads/accident_manifest.json')
        ]);
        if (!manifestResponse.ok || !accidentsResponse.ok) throw new Error('Arquivos das rodovias ainda não foram gerados.');
        const [segments, accidents] = await Promise.all([manifestResponse.json(), accidentsResponse.json()]);
        availableRoads = new Set(accidents.map(String));
        const select = document.getElementById('filter-br');
        select.innerHTML = '<option value="">Escolha uma BR</option>' + segments
            .filter(route => availableRoads.has(String(route.br)))
            .map(route => `<option value="${route.br}">BR-${route.br}</option>`).join('');
        document.getElementById('map-status').textContent = `${availableRoads.size} rodovias com acidentes disponíveis. Clique em uma linha ou escolha uma BR.`;
    } catch (error) {
        document.getElementById('map-status').textContent = 'Os dados dos trajetos não estão disponíveis. Gere os dados atualizados para habilitar a seleção por BR.';
        console.error('Rodovias:', error);
    }
}

async function carregarMapa() {
    const sequence = ++mapLoadSequence;
    const filters = {
        ano: document.getElementById('filter-ano').value,
        uf: document.getElementById('filter-uf').value,
        br: document.getElementById('filter-br').value
    };
    const status = document.getElementById('map-status');
    const roadFilterChanged = !renderedMapFilterState
        || renderedMapFilterState.uf !== filters.uf
        || renderedMapFilterState.br !== filters.br;
    status.textContent = 'Atualizando o mapa com os filtros selecionados…';
    if (accidentPointsLayer) accidentPointsLayer.clearLayers();
    if (accidentHeatLayer) accidentHeatLayer.setLatLngs([]);
    if (roadFilterChanged) {
        if (roadLayer && map?.hasLayer(roadLayer)) map.removeLayer(roadLayer);
        if (roadGlowLayer && map?.hasLayer(roadGlowLayer)) map.removeLayer(roadGlowLayer);
        roadLayer = null;
        roadGlowLayer = null;
    }

    try {
        const selectedBr = filters.br;
        let registros;

        if (selectedBr) {
            const [geometry, rows, boundary, states] = await Promise.all([
                carregarJsonEmCache(roadGeometries, 'all', '/data/roads/all.geojson'),
                carregarJsonEmCache(roadAccidents, selectedBr, `/data/roads/accidents/br_${selectedBr}.json`),
                carregarJsonEmCache(roadGeometries, 'brazil', '/data/roads/brazil.geojson'),
                carregarJsonEmCache(roadGeometries, 'states', '/data/roads/states.geojson')
            ]);
            if (sequence !== mapLoadSequence) return;
            if (!Array.isArray(rows)) throw new Error(`Os dados de acidentes da BR-${selectedBr} estão em formato inválido.`);
            registros = rows.filter(row => (!filters.ano || String(row[11]) === filters.ano) && (!filters.uf || row[2] === filters.uf))
                .map(row => ({ latitude: row[0], longitude: row[1], uf: row[2], municipio: row[3], data: row[4], horario: row[5], causa_acidente: row[6], classificacao_acidente: row[7], mortos: row[8], feridos: row[9], km: row[10], ano: row[11] }));
            status.textContent = `BR-${selectedBr}: ${formatNum(registros.length)} acidentes no recorte atual${registros.length > 2500 ? ' (até 2.500 pontos exibidos)' : ''}. O filtro BR afeta o mapa.`;
            window.selectedRoadGeometry = { geometry, br: selectedBr };
            window.brazilBoundary = boundary;
            window.brazilStates = states;
        } else {
            const [mapRows, geometry, boundary, states] = await Promise.all([
                fetchJsonComTimeout(getUrlComFiltros('/api/mapa', filters)),
                carregarJsonEmCache(roadGeometries, 'all', '/data/roads/all.geojson').catch(() => null),
                carregarJsonEmCache(roadGeometries, 'brazil', '/data/roads/brazil.geojson').catch(() => null),
                carregarJsonEmCache(roadGeometries, 'states', '/data/roads/states.geojson').catch(() => null)
            ]);
            registros = mapRows;
            if (!Array.isArray(registros)) throw new Error('A resposta da API do mapa está em formato inválido.');
            if (sequence !== mapLoadSequence) return;
            status.textContent = filters.uf
                ? `Mapa filtrado para ${filters.uf}${filters.ano ? ` · ${filters.ano}` : ''}. Clique em uma BR ou escolha uma rodovia no seletor.`
                : `Mapa filtrado${filters.ano ? ` para ${filters.ano}` : ''}. Clique em uma BR ou escolha uma rodovia no seletor.`;
            window.selectedRoadGeometry = geometry ? { geometry, br: '' } : null;
            window.brazilBoundary = boundary;
            window.brazilStates = states;
        }

        if (!map) {
            const brazilBounds = L.latLngBounds([-34.0, -74.0], [5.4, -34.7]);
            const brazilPanBounds = L.latLngBounds([-36.0, -76.0], [7.5, -32.0]);
            map = L.map('mapContainer', {
                zoomControl: true,
                attributionControl: true,
                maxBounds: brazilPanBounds,
                maxBoundsViscosity: 0.95,
                minZoom: 3
            });

            [
                ['countryPane', 400], ['statePane', 410], ['roadGlowPane', 420],
                ['roadPane', 430], ['accidentPane', 440]
            ].forEach(([name, zIndex]) => {
                map.createPane(name);
                map.getPane(name).style.zIndex = String(zIndex);
            });
            map.getPane('overlayPane').style.zIndex = '425';

            map.attributionControl.setPrefix('');
            map.attributionControl.addAttribution('Limites: IBGE · Rodovias: DNIT/Infra S.A. · Ocorrências: PRF');

            accidentPointsLayer = L.layerGroup();
            accidentPointsRenderer = L.canvas({ pane: 'accidentPane', padding: 0.5 });
            accidentHeatLayer = L.heatLayer ? L.heatLayer([], {
                radius: 14,
                blur: 8,
                minOpacity: 0.08,
                maxZoom: 8,
                max: 1,
                gradient: { 0.15: '#00c8ff', 0.35: '#54e18b', 0.6: '#ffd84a', 0.82: '#ff832e', 1: '#ff3b4f' }
            }) : null;
            if (!accidentHeatLayer) {
                const heatButton = document.querySelector('[data-map-mode="heat"]');
                if (heatButton) {
                    heatButton.disabled = true;
                    heatButton.title = 'A biblioteca de mapa de calor não carregou.';
                }
            }
            setAccidentMode(accidentMode);
            map.fitBounds(brazilBounds, { padding: [18, 18] });
            map.on('zoomend', atualizarRaioPontos);
            window.addEventListener('resize', () => map && map.invalidateSize());
        } else {
            accidentPointsLayer.clearLayers();
            if (accidentHeatLayer) accidentHeatLayer.setLatLngs([]);
        }

        if (window.brazilBoundary && window.brazilStates) mostrarMapaBrasil(window.brazilBoundary, window.brazilStates);

        if (window.selectedRoadGeometry) {
            mostrarGeometriaRodovia(window.selectedRoadGeometry.geometry, selectedBr, filters.uf);
        } else if (roadLayer) {
            map.removeLayer(roadLayer);
            roadLayer = null;
            if (roadGlowLayer) map.removeLayer(roadGlowLayer);
            roadGlowLayer = null;
        }

        if (sequence !== mapLoadSequence) return;
        renderedMapFilterState = { uf: filters.uf, br: filters.br };
        if (!selectedBr) ajustarEnquadramentoMapa(filters.uf);
        const fullCount = registros.length;
        if (fullCount > 2500) {
            // Stable sampling keeps the map responsive while retaining broad geographic coverage.
            const stride = Math.ceil(fullCount / 2500);
            registros = registros.filter((_, index) => index % stride === 0).slice(0, 2500);
        }

        const popupStyle = `
            font-family:'Space Mono',monospace;
            background:#060d1a;
            color:#e8eaf2;
            border:1px solid rgba(0,200,255,0.2);
            border-radius:10px;
            padding:0;
            min-width:220px;
        `;

        const heatPoints = [];
        registros.forEach(r => {
            const mortosCor  = r.mortos > 0  ? '#ff4040' : '#6b7280';
            const feridosCor = r.feridos > 0 ? '#FF6B35' : '#6b7280';

            const popup = L.popup({ maxWidth: 280, className: 'custom-popup' }).setContent(`
                <div style="${popupStyle}">
                    <div style="background:rgba(0,200,255,0.08);padding:10px 14px;border-bottom:1px solid rgba(0,200,255,0.1);border-radius:10px 10px 0 0;">
                        <div style="font-size:0.7rem;color:#6b7280;letter-spacing:1px;text-transform:uppercase;">${selectedBr ? `BR-${selectedBr} · KM ${r.km ?? '—'}` : 'Município'}</div>
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

            const hasDeaths = Number(r.mortos) > 0;
            heatPoints.push([r.latitude, r.longitude, hasDeaths ? 0.55 : 0.32]);
            const point = L.circleMarker([r.latitude, r.longitude], {
                renderer: accidentPointsRenderer,
                radius: calcularRaioPonto(hasDeaths),
                color: '#f8fafc',
                weight: 1,
                opacity: 0.95,
                fillColor: hasDeaths ? '#ff3b4f' : '#00e5ff',
                fillOpacity: 0.9
            }).bindPopup(popup);
            point.hasDeaths = hasDeaths;
            accidentPointsLayer.addLayer(point);
        });
        if (accidentHeatLayer) accidentHeatLayer.setLatLngs(heatPoints);
        setAccidentMode(accidentMode);

    } catch(e) {
        if (sequence !== mapLoadSequence) return;
        if (accidentPointsLayer) accidentPointsLayer.clearLayers();
        if (accidentHeatLayer) accidentHeatLayer.setLatLngs([]);
        status.textContent = 'Não foi possível atualizar o mapa. Tente alterar o filtro novamente.';
        console.error('Mapa:', e);
    }
}

function ajustarEnquadramentoMapa(uf) {
    if (!map) return;
    if (uf && stateLayer) {
        const code = UF_IBGE_CODES[uf];
        const bounds = L.latLngBounds();
        stateLayer.eachLayer(layer => {
            const feature = layer.feature || {};
            const stateCode = String(feature.properties?.codarea ?? feature.id ?? '').padStart(2, '0');
            if (stateCode === code) bounds.extend(layer.getBounds());
        });
        if (bounds.isValid()) {
            map.fitBounds(bounds, { padding: [28, 28], maxZoom: 6 });
            return;
        }
    }
    if (countryLayer) map.fitBounds(countryLayer.getBounds(), { padding: [18, 18] });
}

async function carregarJsonEmCache(cache, br, url) {
    if (!cache.has(br)) {
        cache.set(br, fetchJsonComTimeout(url, 30000));
    }
    const pending = cache.get(br);
    try {
        return await pending;
    } catch (error) {
        if (cache.get(br) === pending) cache.delete(br);
        throw error;
    }
}

async function fetchJsonComTimeout(url, timeoutMs = 20000) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const response = await fetch(url, { signal: controller.signal });
        if (!response.ok) throw new Error(`Falha ao carregar ${url} (${response.status})`);
        return await response.json();
    } finally {
        clearTimeout(timeout);
    }
}

function calcularRaioPonto(hasDeaths) {
    const zoom = map?.getZoom() ?? 4;
    const base = Math.max(1.3, Math.min(3.4, 1.3 + (zoom - 4) * 0.42));
    return base + (hasDeaths ? 0.4 : 0);
}

function atualizarRaioPontos() {
    if (!accidentPointsLayer) return;
    accidentPointsLayer.eachLayer(point => point.setRadius(calcularRaioPonto(point.hasDeaths)));
}

function setAccidentMode(mode) {
    if (!['points', 'heat', 'none'].includes(mode)) return;
    if (mode === 'heat' && !accidentHeatLayer) return;
    accidentMode = mode;
    document.querySelectorAll('[data-map-mode]').forEach(button => {
        button.setAttribute('aria-pressed', String(button.dataset.mapMode === mode));
    });
    if (!map || !accidentPointsLayer) return;

    const showPoints = mode === 'points';
    const showHeat = mode === 'heat';
    if (map.hasLayer(accidentPointsLayer) !== showPoints) {
        showPoints ? map.addLayer(accidentPointsLayer) : map.removeLayer(accidentPointsLayer);
    }
    if (accidentHeatLayer && map.hasLayer(accidentHeatLayer) !== showHeat) {
        showHeat ? map.addLayer(accidentHeatLayer) : map.removeLayer(accidentHeatLayer);
    }
}

function mostrarMapaBrasil(country, states) {
    if (countryLayer || !map) return;
    countryLayer = L.geoJSON(country, {
        pane: 'countryPane',
        style: { color: '#00d7f5', weight: 2, opacity: 0.9, fillColor: '#0a1728', fillOpacity: 1 },
        interactive: false
    }).addTo(map);
    const stateColors = ['#0b1c30', '#0d2036', '#0a1a2e', '#0c2239'];
    const stateNames = {
        '11': 'Rondônia', '12': 'Acre', '13': 'Amazonas', '14': 'Roraima', '15': 'Pará', '16': 'Amapá', '17': 'Tocantins',
        '21': 'Maranhão', '22': 'Piauí', '23': 'Ceará', '24': 'Rio Grande do Norte', '25': 'Paraíba', '26': 'Pernambuco',
        '27': 'Alagoas', '28': 'Sergipe', '29': 'Bahia', '31': 'Minas Gerais', '32': 'Espírito Santo', '33': 'Rio de Janeiro',
        '35': 'São Paulo', '41': 'Paraná', '42': 'Santa Catarina', '43': 'Rio Grande do Sul', '50': 'Mato Grosso do Sul',
        '51': 'Mato Grosso', '52': 'Goiás', '53': 'Distrito Federal'
    };
    stateLayer = L.geoJSON(states, {
        pane: 'statePane',
        style: feature => {
            const id = Number(feature.id ?? feature.properties?.id ?? feature.properties?.codarea ?? 0);
            return {
                color: '#1b4664',
                weight: 1,
                opacity: 0.9,
                fillColor: stateColors[Math.abs(id) % stateColors.length],
                fillOpacity: 0.88
            };
        },
        onEachFeature: (feature, layer) => {
            const properties = feature.properties || {};
            const code = String(properties.codarea || feature.id || '');
            const name = properties.nome || properties.NM_UF || properties.name || stateNames[code] || 'Estado';
            layer.bindTooltip(name, { sticky: true, className: 'map-state-tooltip' });
        }
    }).addTo(map);
}

function mostrarGeometriaRodovia(collection, br, uf) {
    if (roadLayer) map.removeLayer(roadLayer);
    if (roadGlowLayer) map.removeLayer(roadGlowLayer);
    const visibleRoute = feature => (!uf || feature.properties.uf === uf) && (!br || feature.properties.br === br);

    if (br) {
        roadGlowLayer = L.geoJSON(collection, {
            pane: 'roadGlowPane',
            renderer: L.canvas({ pane: 'roadGlowPane', padding: 0.5 }),
            filter: visibleRoute,
            interactive: false,
            style: { color: '#00b8ff', weight: 12, opacity: 0.28 }
        }).addTo(map);
    } else {
        roadGlowLayer = null;
    }

    roadLayer = L.geoJSON(collection, {
        pane: 'roadPane',
        renderer: L.canvas({ pane: 'roadPane', padding: 0.5 }),
        filter: visibleRoute,
        style: br
            ? { color: '#00e5ff', weight: 5, opacity: 1 }
            : { color: '#00a9c7', weight: 1.8, opacity: 0.58 },
        onEachFeature: (feature, layer) => {
            const featureBr = String(feature.properties.br);
            layer.bindTooltip(`BR-${featureBr}${feature.properties.uf ? ` · ${feature.properties.uf}` : ''}`);
            layer.on('click', () => {
                const select = document.getElementById('filter-br');
                if (!availableRoads.has(featureBr)) {
                    document.getElementById('map-status').textContent = `BR-${featureBr}: sem acidentes registrados nesta base.`;
                    return;
                }
                select.value = featureBr;
                carregarMapa();
            });
        }
    }).addTo(map);
    if (br) {
        const selectedSegments = L.geoJSON(collection, { filter: feature => feature.properties.br === br && (!uf || feature.properties.uf === uf) });
        const bounds = selectedSegments.getBounds();
        if (bounds.isValid()) map.fitBounds(bounds, { padding: [32, 32], maxZoom: 8 });
    }
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

