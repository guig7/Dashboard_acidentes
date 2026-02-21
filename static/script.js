// Configuração Global de Cores para o Chart.js
Chart.defaults.color = '#a0a0b0';
Chart.defaults.font.family = 'Inter, sans-serif';

const colors = {
    accent: '#00d2ff',
    accentSecondary: '#3a7bd5',
    hazard: '#ff4b4b',
    warning: '#ffb84d',
    gridLines: 'rgba(255, 255, 255, 0.05)'
};

let chartEvolucao = null;
let chartMortos = null;
let chartCausas = null;
let chartEstados = null;
let chartHeatmap = null;
let chartRanking = null;
let map = null;
let markerClusterGroup = null;

function getUrlComFiltros(basePath) {
    const ano = document.getElementById('filter-ano').value;
    const uf = document.getElementById('filter-uf').value;
    const params = new URLSearchParams();
    if (ano) params.append('ano', ano);
    if (uf) params.append('uf', uf);
    const qs = params.toString();
    return qs ? `${basePath}?${qs}` : basePath;
}

function carregarTudo() {
    carregarResumo();
    carregarTaxaSeveridade();
    carregarEvolucaoAno();
    carregarMortosAno();
    carregarTopCausas();
    carregarHeatmapHorarios();
    carregarEstados();
    carregarRankingEstados();
    carregarMapa();
}

document.addEventListener('DOMContentLoaded', () => {
    // Pequeno delay para garantir que o DOM está pronto
    setTimeout(() => {
        carregarTudo();
    }, 100);

    document.getElementById('filter-ano').addEventListener('change', carregarTudo);
    document.getElementById('filter-uf').addEventListener('change', carregarTudo);
});

// Funções de formatação
const formatNum = (num) => new Intl.NumberFormat('pt-BR').format(num);

// Carregar Taxa de Severidade
async function carregarTaxaSeveridade() {
    try {
        const res = await fetch(getUrlComFiltros('/api/taxa_severidade'));
        const data = await res.json();

        if (Object.keys(data).length === 0) return;

        document.getElementById('kpi_severidade').textContent = data.taxa_atual.toFixed(2) + '%';
        
        // Comparativo
        let comparativo = '-';
        if (data.taxa_anterior > 0) {
            const sinal = data.variacao >= 0 ? '↑' : '↓';
            const cor = data.variacao >= 0 ? 'var(--hazard)' : 'var(--accent)';
            const texto = data.variacao >= 0 ? 'Piora' : 'Melhora';
            comparativo = `${sinal} ${Math.abs(data.variacao).toFixed(2)}% ${texto}`;
            document.getElementById('kpi_comparativo').style.color = cor;
        }
        document.getElementById('kpi_comparativo').textContent = comparativo;
    } catch (e) {
        console.error("Erro ao carregar taxa de severidade:", e);
    }
}

// Carregar Cards Resumo
async function carregarResumo() {
    try {
        const res = await fetch(getUrlComFiltros('/api/stats_gerais'));
        const data = await res.json();

        // Counter Animation effect
        animateValue("total_acidentes", 0, data.total_acidentes, 1500);
        animateValue("total_mortos", 0, data.total_mortos, 1500);
        animateValue("total_feridos", 0, data.total_feridos, 1500);
    } catch (e) {
        console.error("Erro ao carregar resumo:", e);
    }
}

// 1. Gráfico de Evolução (Line)
async function carregarEvolucaoAno() {
    try {
        const res = await fetch(getUrlComFiltros('/api/acidentes_por_ano'));
        const data = await res.json();

        const ctx = document.getElementById('evolucaoAcidentes').getContext('2d');

        // Gradient fill
        let gradient = ctx.createLinearGradient(0, 0, 0, 400);
        gradient.addColorStop(0, 'rgba(0, 210, 255, 0.5)');
        gradient.addColorStop(1, 'rgba(0, 210, 255, 0.0)');

        if (chartEvolucao) chartEvolucao.destroy();

        chartEvolucao = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [{
                    label: 'Total de Acidentes',
                    data: data.data,
                    borderColor: colors.accent,
                    backgroundColor: gradient,
                    borderWidth: 3,
                    pointBackgroundColor: colors.bgCard,
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
    } catch (e) {
        console.error(e);
    }
}

// 2. Gráfico de Vítimas Fatais (Bar/Line)
async function carregarMortosAno() {
    try {
        const res = await fetch(getUrlComFiltros('/api/mortos_por_ano'));
        const data = await res.json();

        const ctx = document.getElementById('evolucaoMortos').getContext('2d');

        let gradient = ctx.createLinearGradient(0, 0, 0, 400);
        gradient.addColorStop(0, 'rgba(255, 75, 75, 0.8)');
        gradient.addColorStop(1, 'rgba(255, 75, 75, 0.2)');

        if (chartMortos) chartMortos.destroy();

        chartMortos = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{
                    label: 'Total de Mortos',
                    data: data.data,
                    backgroundColor: gradient,
                    borderRadius: 6,
                    barPercentage: 0.6
                }]
            },
            options: chartOptions()
        });
    } catch (e) {
        console.error(e);
    }
}

// 3. Top Causas (Doughnut ou Horizontal Bar)
async function carregarTopCausas() {
    try {
        const res = await fetch(getUrlComFiltros('/api/causas'));
        const data = await res.json();

        const ctx = document.getElementById('topCausas').getContext('2d');

        if (chartCausas) chartCausas.destroy();

        chartCausas = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: data.labels,
                datasets: [{
                    data: data.data,
                    backgroundColor: [
                        '#00d2ff', '#3a7bd5', '#ff4b4b', '#ffb84d',
                        '#b84dff', '#4dffb8', '#ff4d94', '#e6e600',
                        '#8c8c8c', '#ffffff'
                    ],
                    borderWidth: 0,
                    hoverOffset: 10
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: { boxWidth: 12, font: { size: 10 } }
                    },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                let label = context.label || '';
                                let value = context.parsed;
                                return `${label}: ${formatNum(value)}`;
                            }
                        }
                    }
                },
                cutout: '70%'
            }
        });
    } catch (e) {
        console.error(e);
    }
}

// 4. Estados (Radar ou Bar Horizontal)
async function carregarEstados() {
    try {
        const res = await fetch(getUrlComFiltros('/api/estados'));
        const data = await res.json();

        // Pegando os top 15 para nao poluir o grafico e ficar legível
        const labels = data.labels.slice(0, 15);
        const values = data.data.slice(0, 15);

        const ctx = document.getElementById('acidentesEstados').getContext('2d');

        let gradient = ctx.createLinearGradient(0, 0, 400, 0); // horizontal
        gradient.addColorStop(0, '#3a7bd5');
        gradient.addColorStop(1, '#00d2ff');

        if (chartEstados) chartEstados.destroy();

        chartEstados = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Acidentes (Top 15)',
                    data: values,
                    backgroundColor: gradient,
                    borderRadius: 4
                }]
            },
            options: {
                ...chartOptions(),
                indexAxis: 'y', // Bar horizontal
            }
        });
    } catch (e) {
        console.error(e);
    }
}

// Utilitário global para opções de gráficos de barras/linhas
function chartOptions() {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                titleFont: { size: 13, family: 'Inter' },
                bodyFont: { size: 14, family: 'Inter', weight: 'bold' },
                padding: 12,
                cornerRadius: 8,
                callbacks: {
                    label: function (context) {
                        return `${context.dataset.label}: ${formatNum(context.parsed.y || context.parsed.x)}`;
                    }
                }
            }
        },
        scales: {
            x: {
                grid: { display: false, drawBorder: false },
                ticks: { font: { family: 'Inter' } }
            },
            y: {
                grid: { color: colors.gridLines, drawBorder: false },
                ticks: {
                    font: { family: 'Inter' },
                    callback: function (value) {
                        if (value >= 1000) return value / 1000 + 'k';
                        return value;
                    }
                }
            }
        }
    };
}

// Animação de contagem para números (Efeito visual premium)
function animateValue(id, start, end, duration) {
    if (start === end) return;
    let range = end - start;
    let current = start;
    let increment = end > start ? 1 : -1;
    // Calc steps based on range to prevent infinite loops or freezing
    let stepTime = Math.abs(Math.floor(duration / Math.min(range, 200)));
    // If range is huge, we jump more than 1 per step
    let stepAmount = Math.ceil(range / (duration / 16));
    let obj = document.getElementById(id);

    let timer = setInterval(function () {
        current += stepAmount;
        if ((stepAmount > 0 && current >= end) || (stepAmount < 0 && current <= end)) {
            current = end;
            clearInterval(timer);
        }
        obj.innerHTML = formatNum(current);
    }, 16); // 60fps
}

// Mapa com Leaflet
async function carregarMapa() {
    try {
        const res = await fetch(getUrlComFiltros('/api/mapa'));
        const coordenadas = await res.json();

        // Inicializar mapa se não existir
        if (!map) {
            map = L.map('mapContainer', {
                zoomControl: true,
                attributionControl: true
            }).setView([-14.2, -51.9], 4); // Centro do Brasil
            
            // Tile Layer (OpenStreetMap)
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors',
                maxZoom: 19,
                opacity: 0.8
            }).addTo(map);

            // Cluster de markers
            markerClusterGroup = L.markerClusterGroup({
                maxClusterRadius: 80,
                iconCreateFunction: function (cluster) {
                    const count = cluster.getChildCount();
                    let size = 'small';
                    let color = '#00d2ff';
                    
                    if (count > 100) {
                        size = 'large';
                        color = '#ff4b4b';
                    } else if (count > 50) {
                        size = 'medium';
                        color = '#ffb84d';
                    }
                    
                    return new L.DivIcon({
                        html: `<div style="background-color: ${color}; border-radius: 50%; display: flex; align-items: center; justify-content: center; width: 40px; height: 40px; font-weight: bold; color: white; font-size: 14px;">${count}</div>`,
                        iconSize: [40, 40]
                    });
                }
            });
            map.addLayer(markerClusterGroup);
            
            // Redraw map on window resize
            window.addEventListener('resize', function() {
                if (map) map.invalidateSize();
            });
        } else {
            // Limpar markers antigos
            markerClusterGroup.clearLayers();
        }

        // Adicionar markers
        if (coordenadas.length > 0) {
            const markers = coordenadas.map(coord => {
                return L.marker([coord[0], coord[1]], {
                    icon: L.icon({
                        iconUrl: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%2300d2ff" stroke="white" stroke-width="2"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"/></svg>',
                        iconSize: [24, 24],
                        iconAnchor: [12, 12]
                    })
                });
            });

            // Adicionar ao cluster
            markerClusterGroup.addLayers(markers);
        }

        // Zoom automático ao tamanho dos dados
        if (markerClusterGroup.getLayers().length > 0) {
            const group = new L.featureGroup(markerClusterGroup.getLayers());
            map.fitBounds(group.getBounds(), { padding: [50, 50] });
        }

    } catch (e) {
        console.error("Erro ao carregar mapa:", e);
    }
}

// Heatmap de Horários
async function carregarHeatmapHorarios() {
    try {
        const res = await fetch(getUrlComFiltros('/api/heatmap_horarios'));
        const data = await res.json();

        console.log("Dados Heatmap recebidos:", data);

        if (Object.keys(data).length === 0 || !data.labels) {
            console.warn("Heatmap: dados vazios");
            return;
        }

        const canvas = document.getElementById('heatmapHorarios');
        if (!canvas) {
            console.error("Canvas heatmapHorarios não encontrado");
            return;
        }

        if (chartHeatmap) chartHeatmap.destroy();

        const ctx = canvas.getContext('2d');
        chartHeatmap = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [
                    {
                        label: 'Acidentes',
                        data: data.acidentes,
                        backgroundColor: 'rgba(0, 210, 255, 0.6)',
                        borderColor: colors.accent,
                        borderWidth: 1,
                        borderRadius: 4,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Taxa de Severidade (%)',
                        data: data.severidade,
                        type: 'line',
                        borderColor: colors.hazard,
                        backgroundColor: 'transparent',
                        borderWidth: 3,
                        pointBackgroundColor: colors.hazard,
                        pointBorderColor: 'white',
                        pointBorderWidth: 2,
                        pointRadius: 4,
                        yAxisID: 'y1',
                        tension: 0.4,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        labels: { font: { family: 'Inter' }, color: colors.accent, padding: 15 }
                    }
                },
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        grid: { color: colors.gridLines, drawBorder: false },
                        ticks: { color: colors.accent }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        grid: { display: false, drawOnChartArea: false },
                        ticks: { color: colors.hazard },
                        title: { display: true, text: 'Severidade (%)', color: colors.hazard }
                    },
                    x: {
                        grid: { color: colors.gridLines, drawBorder: false },
                        ticks: { color: colors.accent }
                    }
                }
            }
        });

        console.log("Gráfico Heatmap criado com sucesso");
    } catch (e) {
        console.error("Erro ao carregar heatmap:", e);
    }
}

// Ranking de Estados por Severidade
async function carregarRankingEstados() {
    try {
        const res = await fetch(getUrlComFiltros('/api/ranking_estados'));
        const data = await res.json();

        console.log("Dados Ranking recebidos:", data);

        if (Object.keys(data).length === 0 || !data.labels || data.labels.length === 0) {
            console.warn("Ranking: dados vazios");
            return;
        }

        const ctx = document.getElementById('rankingEstados');
        if (!ctx) {
            console.error("Canvas rankingEstados não encontrado");
            return;
        }

        const canvasCtx = ctx.getContext('2d');

        // Criar gradient colors baseado em severidade (valores típicos: 10-23%)
        const gradientColors = data.taxa_severidade.map(taxa => {
            if (taxa > 15) return colors.hazard;      // Vermelho: > 15%
            if (taxa > 12) return colors.warning;      // Laranja: > 12%
            return colors.accent;                       // Azul: < 12%
        });

        console.log("Cores atribuídas:", gradientColors);

        if (chartRanking) chartRanking.destroy();

        chartRanking = new Chart(canvasCtx, {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{
                    label: 'Taxa de Severidade (%)',
                    data: data.taxa_severidade,
                    backgroundColor: gradientColors,
                    borderColor: 'rgba(255, 255, 255, 0.2)',
                    borderWidth: 1,
                    borderRadius: 6
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        max: 25,
                        grid: { color: colors.gridLines, drawBorder: false },
                        ticks: { color: colors.accent, callback: function(value) { return value + '%'; } }
                    },
                    y: {
                        grid: { color: colors.gridLines, drawBorder: false },
                        ticks: { color: colors.accent }
                    }
                }
            }
        });

        console.log("Gráfico Ranking criado com sucesso");
    } catch (e) {
        console.error("Erro ao carregar ranking:", e);
    }
}

// Mostrar/ocultar tabela
const btnTabela = document.getElementById('btnTabelaDetalhada');
const tabelaContainer = document.getElementById('tabelaDetalhadaContainer');
if (btnTabela) {
    btnTabela.addEventListener('click', () => {
        if (tabelaContainer.style.display === 'none') {
            tabelaContainer.style.display = 'block';
            carregarTabelaDetalhada();
            btnTabela.textContent = 'Ocultar Tabela';
        } else {
            tabelaContainer.style.display = 'none';
            btnTabela.textContent = 'Ver Tabela Detalhada';
        }
    });
}
