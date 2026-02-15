let graficoUnidades = null;
let graficoNotas = null;
let graficoLogin = null;


// 🔹 Função chamada pelo botão
window.aplicarFiltro = function () {

    const dataInicio = document.getElementById("dataInicio")?.value;
    const dataFim = document.getElementById("dataFim")?.value;

    if (!dataInicio || !dataFim) {
        console.warn("Selecione o intervalo de datas");
        return;
    }

    fetch(`/dashboard/stats?dataInicio=${dataInicio}&dataFim=${dataFim}`)
        .then(response => response.json())
        .then(data => atualizarDashboard(data))
        .catch(error => console.error("Erro ao buscar dados:", error));
};


// 🔹 Carrega automaticamente ao abrir
document.addEventListener("DOMContentLoaded", function () {
    window.aplicarFiltro();
});


// 🔹 Atualiza cards + gráficos
function atualizarDashboard(data) {

    // =========================
    // ATUALIZA CARDS
    // =========================
    document.getElementById("totalUnits").innerText =
        data.total_units ?? 0;

    document.getElementById("totalNotasFechadas").innerText =
        data.total_notas_fechadas ?? 0;

    document.getElementById("totalNotasPendentes").innerText =
        data.total_notas_pendentes ?? 0;


    // =========================
    // 🟡 UNIDADES POR DIA
    // =========================
    const diasUnits = Object.keys(data.unidades_por_dia || {});
    const valoresUnits = Object.values(data.unidades_por_dia || {});

    if (graficoUnidades) graficoUnidades.destroy();

    graficoUnidades = new Chart(
        document.getElementById("graficoUnidadesDia"),
        {
            data: {
                labels: diasUnits,
                datasets: [
                    {
                        type: "bar",
                        label: "Units Recebidas",
                        data: valoresUnits
                    },
                    {
                        type: "line",
                        label: "Tendência Units",
                        data: valoresUnits
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        }
    );


    // =========================
    // 🟢 NOTAS POR DIA
    // =========================
    const diasNotas = Object.keys(data.notas_por_dia || {});
    const valoresNotas = Object.values(data.notas_por_dia || {});

    if (graficoNotas) graficoNotas.destroy();

    graficoNotas = new Chart(
        document.getElementById("graficoNotasDia"),
        {
            data: {
                labels: diasNotas,
                datasets: [
                    {
                        type: "bar",
                        label: "Notas Recebidas",
                        data: valoresNotas
                    },
                    {
                        type: "line",
                        label: "Tendência Notas",
                        data: valoresNotas
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        }
    );


    // =========================
    // 🔵 POR LOGIN
    // =========================
    const logins = Object.keys(data.por_login || {});
    const unitsLogin = logins.map(l => data.por_login[l].units);
    const notasLogin = logins.map(l => data.por_login[l].notas);

    if (graficoLogin) graficoLogin.destroy();

    graficoLogin = new Chart(
        document.getElementById("graficoPorLogin"),
        {
            type: "bar",
            data: {
                labels: logins,
                datasets: [
                    {
                        label: "Units",
                        data: unitsLogin
                    },
                    {
                        label: "Notas",
                        data: notasLogin
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        }
    );
}
