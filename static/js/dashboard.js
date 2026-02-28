// ======================================
// 📊 VARIÁVEIS GLOBAIS DOS GRÁFICOS
// ======================================

let graficoUnidades = null;
let graficoNotas = null;
let graficoLogin = null;
let graficoDeletadas = null;
let graficoCargas = null;
let graficoNoShowDia = null;
let graficoNoShow = null;

// ======================================
// 🔹 PLUGIN PARA MOSTRAR VALORES NAS COLUNAS
// ======================================

const pluginDataLabels = {
    id: "dataLabels",
    afterDatasetsDraw(chart) {
        const { ctx } = chart;

        chart.data.datasets.forEach((dataset, i) => {
            const meta = chart.getDatasetMeta(i);

            meta.data.forEach((bar, index) => {
                const data = dataset.data[index];
                if (data === 0) return;

                ctx.save();
                ctx.fillStyle = document.body.classList.contains("dark-mode")
                    ? "#e5e7eb"
                    : "#1f2937";

                ctx.font = "600 11px Inter";
                ctx.textAlign = "center";
                ctx.fillText(data, bar.x, bar.y - 8);
            });
        });
    }
};


// ======================================
// 🔹 BOTÃO FILTRO
// ======================================

window.aplicarFiltro = function () {

    const dataInicio = document.getElementById("dataInicio")?.value;
    const dataFim = document.getElementById("dataFim")?.value;

    if (!dataInicio || !dataFim) {
        console.warn("Selecione o intervalo de datas");
        return;
    }

    fetch(`/dashboard/stats?dataInicio=${dataInicio}&dataFim=${dataFim}`)
        .then(res => res.json())
        .then(dados => atualizarDashboard(dados))
        .catch(err => console.error("Erro:", err));
};


// ======================================
// 🔹 AUTO LOAD
// ======================================

document.addEventListener("DOMContentLoaded", function () {

    const hoje = new Date().toISOString().split("T")[0];

    document.getElementById("dataInicio").value = hoje;
    document.getElementById("dataFim").value = hoje;

    aplicarFiltro();
});


// ======================================
// 🔹 CONFIG PADRÃO ESTILO NOTION
// ======================================

function configPadrao(labels, valores, labelBarra, corBarra) {

    return {
        type: "bar",
        data: {
            labels: labels,
            datasets: [{
                label: labelBarra,
                data: valores,
                backgroundColor: corBarra,
                borderRadius: 12,
                maxBarThickness: 80
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,

            layout: {
                padding: {
                    left: 20,
                    right: 20,
                    top: 10,
                    bottom: 10
                }
            },

            plugins: {
                legend: { display: false }
            },

            scales: {
                x: {
                    grid: { display: false },
                    ticks: {
                        color: "#6b7280",
                        font: { size: 12 }
                    }
                },
                y: {
                    beginAtZero: true,
                    grace: "15%",
                    ticks: {
                        color: "#6b7280",
                        font: { size: 12 }
                    },
                    grid: {
                        color: "rgba(0,0,0,0.04)"
                    }
                }
            }
        },
        plugins: [pluginDataLabels]
    };
}



// ======================================
// 🔹 ATUALIZA DASHBOARD
// ======================================

function atualizarDashboard(data) {

    // =========================
    // 🧾 CARDS COM ANIMAÇÃO
    // =========================

    animarNumero("totalUnits", data.total_units ?? 0);
    animarNumero("totalNotasFechadas", data.total_notas_fechadas ?? 0);
    animarNumero("totalNotasPendentes", data.total_notas_pendentes ?? 0);
    animarNumero("totalNotasAndamento", data.total_notas_andamento ?? 0);
    animarNumero("totalNotasDeletadas", data.total_notas_deletadas ?? 0);
    animarNumero("totalNotasNoShow", data.total_notas_no_show ?? 0);
    animarNumero("totalCargasAtrasadas", data.total_cargas_atrasadas ?? 0);

    renderizarListaAtrasadas(data.cargas_atrasadas || []);

    // =========================
    // 🟡 UNIDADES
    // =========================

    const diasUnits = Object.keys(data.unidades_por_dia || {});
    const valoresUnits = Object.values(data.unidades_por_dia || {});

    if (graficoUnidades) graficoUnidades.destroy();

    graficoUnidades = new Chart(
        document.getElementById("graficoUnidadesDia"),
        configPadrao(diasUnits, valoresUnits, "#3b82f6")
    );



    // =========================
// ⚫ NO SHOW POR DIA
// =========================

const diasNoShow = Object.keys(data.no_show_por_dia || {});
const valoresNoShow = Object.values(data.no_show_por_dia || {});

if (graficoNoShow) graficoNoShow.destroy();

graficoNoShow = new Chart(
    document.getElementById("graficoNoShowDia"),
    configPadrao(diasNoShow, valoresNoShow, "#ef4444")
);



    // =========================
    // 🟢 NOTAS
    // =========================

    const diasNotas = Object.keys(data.notas_por_dia || {});
    const valoresNotas = Object.values(data.notas_por_dia || {});

    if (graficoNotas) graficoNotas.destroy();

    graficoNotas = new Chart(
        document.getElementById("graficoNotasDia"),
        configPadrao(diasNotas, valoresNotas, "#10b981")
    );


    // =========================
    // 🔴 DELETADAS
    // =========================

    const diasDel = Object.keys(data.notas_deletadas_por_dia || {});
    const valoresDel = Object.values(data.notas_deletadas_por_dia || {});

    if (graficoDeletadas) graficoDeletadas.destroy();

    graficoDeletadas = new Chart(
        document.getElementById("graficoNotasDeletadasDia"),
        configPadrao(diasDel, valoresDel, "#ef4444")
    );


    // =========================
    // 🔵 PERFORMANCE LOGIN
    // =========================

    const logins = Object.keys(data.por_login || {});
    const unitsLogin = logins.map(l => data.por_login[l]?.units || 0);
    const notasLogin = logins.map(l => data.por_login[l]?.notas || 0);
    if (graficoLogin) graficoLogin.destroy();

    graficoLogin = new Chart(
        document.getElementById("graficoPorLogin"),
        configPadrao(logins, unitsLogin, "#6366f1")
    );
    // =========================
// 🟣 CARGAS POR AA
// =========================

if (graficoCargas) graficoCargas.destroy();

graficoCargas = new Chart(
    document.getElementById("graficoCargasPorLogin"),
    configPadrao(logins, notasLogin, "Cargas", "#f59e0b")
);
// =========================
// ⚫ NO SHOW DO DIA
// =========================

const qtdNoShow = data.total_notas_no_show || 0;
const unitsNoShow = data.total_units_no_show || 0;

if (graficoNoShowDia) graficoNoShowDia.destroy();

graficoNoShowDia = new Chart(
    document.getElementById("graficoNoShowDia"),
    {
        type: "bar",
        data: {
            labels: ["No Show"],
            datasets: [
                {
                    label: "Quantidade",
                    data: [qtdNoShow],
                    backgroundColor: "#ef4444",
                    borderRadius: 10
                },
                {
                    label: "Units",
                    data: [unitsNoShow],
                    backgroundColor: "#f97316",
                    borderRadius: 10
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    }
);

}


function renderizarListaAtrasadas(cargas) {
    const tbody = document.getElementById("listaCargasAtrasadas");
    if (!tbody) return;

    tbody.innerHTML = "";

    if (!Array.isArray(cargas) || cargas.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="linha-sem-dados">Nenhuma carga em atraso no intervalo selecionado.</td></tr>`;
        return;
    }

    cargas.forEach(carga => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${carga.appointment_id ?? "-"}</td>
            <td>${formatarStatus(carga.status)}</td>
            <td>${formatarDataHora(carga.expected_arrival_date)}</td>
            <td class="atraso-cell">${formatarTempoAtraso(carga.tempo_atraso_segundos)}</td>
            <td>${Number(carga.units ?? 0)}</td>
            <td>${Number(carga.cartons ?? 0)}</td>
            <td>${carga.aa_responsavel ?? "-"}</td>
        `;
        tbody.appendChild(tr);
    });
}

function formatarTempoAtraso(segundos) {
    const t = Math.max(0, Number(segundos || 0));
    const horas = String(Math.floor(t / 3600)).padStart(2, "0");
    const minutos = String(Math.floor((t % 3600) / 60)).padStart(2, "0");
    const seg = String(t % 60).padStart(2, "0");
    return `${horas}:${minutos}:${seg}`;
}

function formatarDataHora(valor) {
    if (!valor) return "-";
    const d = new Date(valor);
    if (Number.isNaN(d.getTime())) return "-";
    return d.toLocaleString("pt-BR");
}

function formatarStatus(status) {
    if (!status) return "-";
    return String(status).replaceAll("_", " ").toUpperCase();
}

// ======================================
// ✨ ANIMAÇÃO SUAVE NOS NÚMEROS
// ======================================

function animarNumero(id, valorFinal, duracao = 800) {

    const elemento = document.getElementById(id);
    let inicio = 0;

    const incremento = valorFinal / (duracao / 16);

    function atualizar() {
        inicio += incremento;

        if (inicio >= valorFinal) {
            elemento.innerText = valorFinal.toLocaleString();
        } else {
            elemento.innerText = Math.floor(inicio).toLocaleString();
            requestAnimationFrame(atualizar);
        }
    }

    atualizar();
}


// ======================================
// 🌙 DARK MODE
// ======================================

function toggleDarkMode() {
    document.body.classList.toggle("dark-mode");
}
