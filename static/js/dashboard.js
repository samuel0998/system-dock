let graficoUnidades = null;
let graficoNotas = null;
let graficoLogin = null;
let graficoDeletadas = null;
let graficoCargas = null;
let dadosDashboard = null;

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
                ctx.fillStyle = document.body.classList.contains("dark-mode") ? "#e5e7eb" : "#1f2937";
                ctx.font = "600 11px Inter";
                ctx.textAlign = "center";
                ctx.fillText(data, bar.x, bar.y - 8);
            });
        });
    }
};

window.aplicarFiltro = function () {
    const dataInicio = document.getElementById("dataInicio")?.value;
    const dataFim = document.getElementById("dataFim")?.value;

    if (!dataInicio || !dataFim) return;

    fetch(`/dashboard/stats?dataInicio=${dataInicio}&dataFim=${dataFim}`)
        .then(res => res.json())
        .then(dados => {
            dadosDashboard = dados;
            atualizarDashboard(dados);
        })
        .catch(err => console.error("Erro:", err));
};

document.addEventListener("DOMContentLoaded", function () {
    const hoje = new Date().toISOString().split("T")[0];
    document.getElementById("dataInicio").value = hoje;
    document.getElementById("dataFim").value = hoje;

    document.getElementById("filtroAtrasoAppointment")?.addEventListener("input", aplicarFiltrosTabelas);
    document.getElementById("filtroProdLogin")?.addEventListener("input", aplicarFiltrosTabelas);

    aplicarFiltro();
});

function configPadrao(labels, valores, labelBarra, corBarra) {
    return {
        type: "bar",
        data: {
            labels,
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
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { display: false } },
                y: { beginAtZero: true, grace: "15%" }
            }
        },
        plugins: [pluginDataLabels]
    };
}

function atualizarDashboard(data) {
    animarNumero("totalUnits", data.total_units ?? 0);
    animarNumero("totalNotasFechadas", data.total_notas_fechadas ?? 0);
    animarNumero("totalNotasPendentes", data.total_notas_pendentes ?? 0);
    animarNumero("totalNotasAndamento", data.total_notas_andamento ?? 0);
    animarNumero("totalNotasDeletadas", data.total_notas_deletadas ?? 0);
    animarNumero("totalNotasNoShow", data.total_notas_no_show ?? 0);
    animarNumero("totalCargasAtrasadas", data.total_cargas_atrasadas ?? 0);

    aplicarFiltrosTabelas();

    const diasUnits = Object.keys(data.unidades_por_dia || {});
    const valoresUnits = Object.values(data.unidades_por_dia || {});
    const diasNotas = Object.keys(data.notas_por_dia || {});
    const valoresNotas = Object.values(data.notas_por_dia || {});
    const diasDel = Object.keys(data.notas_deletadas_por_dia || {});
    const valoresDel = Object.values(data.notas_deletadas_por_dia || {});

    if (graficoUnidades) graficoUnidades.destroy();
    if (graficoNotas) graficoNotas.destroy();
    if (graficoDeletadas) graficoDeletadas.destroy();
    if (graficoLogin) graficoLogin.destroy();
    if (graficoCargas) graficoCargas.destroy();

    graficoUnidades = new Chart(document.getElementById("graficoUnidadesDia"), configPadrao(diasUnits, valoresUnits, "Units", "#3b82f6"));
    graficoNotas = new Chart(document.getElementById("graficoNotasDia"), configPadrao(diasNotas, valoresNotas, "Notas", "#10b981"));
    graficoDeletadas = new Chart(document.getElementById("graficoNotasDeletadasDia"), configPadrao(diasDel, valoresDel, "Deletadas", "#ef4444"));

    const logins = Object.keys(data.por_login || {});
    const produtividadeLogin = logins.map(l => data.por_login[l]?.produtividade_media || 0);
    const notasLogin = logins.map(l => data.por_login[l]?.notas || 0);

    graficoLogin = new Chart(document.getElementById("graficoPorLogin"), configPadrao(logins, produtividadeLogin, "Produtividade (units/h)", "#6366f1"));
    graficoCargas = new Chart(document.getElementById("graficoCargasPorLogin"), configPadrao(logins, notasLogin, "Cargas", "#f59e0b"));
}

function aplicarFiltrosTabelas() {
    if (!dadosDashboard) return;

    const filtroAppointment = (document.getElementById("filtroAtrasoAppointment")?.value || "").toLowerCase();
    const filtroLogin = (document.getElementById("filtroProdLogin")?.value || "").toLowerCase();

    const atrasadas = (dadosDashboard.cargas_atrasadas || []).filter(c =>
        String(c.appointment_id || "").toLowerCase().includes(filtroAppointment)
    );

    const produtividade = Object.entries(dadosDashboard.produtividade_por_aa || {}).filter(([login]) =>
        String(login || "").toLowerCase().includes(filtroLogin)
    );

    renderizarListaAtrasadas(atrasadas);
    renderizarTabelaProdutividade(produtividade);
}

function renderizarListaAtrasadas(cargas) {
    const tbody = document.getElementById("listaCargasAtrasadas");
    if (!tbody) return;

    tbody.innerHTML = "";

    if (!Array.isArray(cargas) || cargas.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="linha-sem-dados">Nenhuma carga em atraso no intervalo selecionado.</td></tr>`;
        return;
    }

    cargas.forEach(carga => {
        const comentario = carga.atraso_comentario
            ? `<button class="btn-balao" title="${escapeHtml(carga.atraso_comentario)}" onclick="alert('${escapeJs(carga.atraso_comentario)}')">💬</button>`
            : "-";

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${carga.appointment_id ?? "-"}</td>
            <td>${formatarStatus(carga.status)}</td>
            <td>${formatarDataHora(carga.expected_arrival_date)}</td>
            <td class="atraso-cell">${formatarTempoAtraso(carga.tempo_atraso_segundos)}</td>
            <td>${Number(carga.units ?? 0)}</td>
            <td>${Number(carga.cartons ?? 0)}</td>
            <td>${carga.aa_responsavel ?? "-"}</td>
            <td>${comentario}</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderizarTabelaProdutividade(rows) {
    const tbody = document.getElementById("tabelaProdutividadeAA");
    if (!tbody) return;

    tbody.innerHTML = "";

    if (!Array.isArray(rows) || rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="linha-sem-dados">Nenhum AA encontrado para o filtro selecionado.</td></tr>`;
        return;
    }

    rows.forEach(([login, dados]) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${login || "-"}</td>
            <td>${Number(dados.units || 0)}</td>
            <td>${Number(dados.horas_produzidas || 0).toFixed(2)} h</td>
            <td>${Number(dados.produtividade_media || 0).toFixed(2)}</td>
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
    return d.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" });
}

function formatarStatus(status) {
    if (!status) return "-";
    return String(status).replaceAll("_", " ").toUpperCase();
}

function escapeHtml(texto) {
    return String(texto ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll("\"", "&quot;")
        .replaceAll("'", "&#039;");
}

function escapeJs(texto) {
    return String(texto ?? "").replaceAll("\\", "\\\\").replaceAll("'", "\\'").replaceAll("\n", "\\n");
}

function animarNumero(id, valorFinal, duracao = 800) {
    const elemento = document.getElementById(id);
    if (!elemento) return;

    let inicio = 0;
    const incremento = valorFinal / (duracao / 16);

    function atualizar() {
        inicio += incremento;
        if (inicio >= valorFinal) {
            elemento.innerText = Number(valorFinal).toLocaleString();
        } else {
            elemento.innerText = Math.floor(inicio).toLocaleString();
            requestAnimationFrame(atualizar);
        }
    }

    atualizar();
}

function toggleDarkMode() {
    document.body.classList.toggle("dark-mode");
}
