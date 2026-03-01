// /static/js/painel.js
// Versão limpa (sem funções duplicadas) + suporte a ARRIVAL_SCHEDULED + SLA 4h em ARRIVAL
// Requisitos do backend (/pc/listar):
// - status: "arrival_scheduled" | "arrival" | "checkin" | "closed" | "no_show" | "deleted"
// - tempo_sla_segundos (number | null) para status arrival e arrival_scheduled (quando aplicável)
// - start_time (ISO | null) para status checkin
// - tempo_total_segundos (number | null) para status closed
// - truck_tipo (string | null)

document.addEventListener("DOMContentLoaded", () => {
    carregarCargas();

    // Se seus botões de filtro chamam via onclick no HTML, ok.
    // Se preferir, pode ativar listeners aqui:
    // document.getElementById("btnFiltrar")?.addEventListener("click", aplicarFiltros);
    // document.getElementById("btnLimpar")?.addEventListener("click", limparFiltros);
});

let timers = {};
let cargasGlobais = [];

// =====================================================
// 🔄 CARREGAR CARGAS
// =====================================================
function carregarCargas() {
    fetch("/pc/listar")
        .then(res => res.json())
        .then(data => {
            if (!Array.isArray(data)) {
                console.error("Resposta inesperada em /pc/listar:", data);
                cargasGlobais = [];
                renderizarTabela([]);
                return;
            }
            cargasGlobais = data;
            renderizarTabela(data);
        })
        .catch(err => {
            console.error("Erro ao carregar cargas:", err);
            cargasGlobais = [];
            renderizarTabela([]);
        });
}

// =====================================================
// 🧱 RENDERIZAR TABELA
// =====================================================
function renderizarTabela(cargas) {

    // Limpa timers antigos
    Object.values(timers).forEach(clearInterval);
    timers = {};

    const tabela = document.getElementById("tabelaCargas");
    if (!tabela) {
        console.error("Elemento #tabelaCargas não encontrado no DOM.");
        return;
    }

    tabela.innerHTML = "";

    cargas.forEach(carga => {

        const tr = document.createElement("tr");
        tr.id = `row-carga-${carga.id}`;
        const prioridade = calcularPrioridade(Number(carga.priority_score ?? 0));

        // Linha vermelha quando SLA negativo (ARRIVAL ou ARRIVAL_SCHEDULED após expected)
        if (
            (carga.status === "arrival" || carga.status === "arrival_scheduled") &&
            typeof carga.tempo_sla_segundos === "number" &&
            carga.tempo_sla_segundos < 0
        ) {
            tr.classList.add("linha-atrasada");
        }

        tr.innerHTML = `
            <td>${renderAppointmentLink(carga.appointment_id)}</td>
            <td>${carga.truck_tipo ?? "-"}</td>
            <td>${formatarData(carga.expected_arrival_date)}</td>
            <td>${Number(carga.units ?? 0)}</td>
            <td>${Number(carga.cartons ?? 0)}</td>
            <td>${formatarStatusLabel(carga.status)}</td>
            <td>${carga.aa_responsavel ?? "-"}</td>
            <td>
                <span class="${prioridade.classe}">
                    ${Number(carga.priority_score ?? 0)} (${prioridade.label})
                </span>
            </td>
            <td id="timer-${carga.id}">
                ${formatarTempoFinal(carga)}
            </td>
            <td>${renderizarBotaoAcao(carga)}</td>
        `;

        tabela.appendChild(tr);

        // Cronômetro se estiver em checkin
        if (carga.status === "checkin" && carga.start_time) {
            iniciarCronometro(carga.id, carga.start_time);
        }

        // Timer SLA em tempo real para arrival / arrival_scheduled
        if (
            (carga.status === "arrival" || carga.status === "arrival_scheduled") &&
            typeof carga.tempo_sla_segundos === "number"
        ) {
            iniciarTimerSLA(carga.id, carga.tempo_sla_segundos, carga.status);
        }
    });
}

// =====================================================
// ⏱ CRONÔMETRO (CHECKIN)
// =====================================================
function iniciarCronometro(id, startTimeISO) {
    const start = new Date(startTimeISO);

    // Se data inválida, não inicia
    if (isNaN(start)) return;

    timers[id] = setInterval(() => {
        const agora = new Date();
        const diff = Math.floor((agora - start) / 1000);
        atualizarTempoTela(id, diff);
    }, 1000);
}

function atualizarTempoTela(id, totalSegundos) {
    const horas = String(Math.floor(totalSegundos / 3600)).padStart(2, "0");
    const minutos = String(Math.floor((totalSegundos % 3600) / 60)).padStart(2, "0");
    const segundos = String(totalSegundos % 60).padStart(2, "0");

    const el = document.getElementById(`timer-${id}`);
    if (el) el.innerText = `${horas}:${minutos}:${segundos}`;
}

function iniciarTimerSLA(id, tempoInicialSegundos, status) {
    const el = document.getElementById(`timer-${id}`);
    if (!el) return;

    const rowEl = document.getElementById(`row-carga-${id}`);

    let restante = Number(tempoInicialSegundos);
    el.innerText = formatarTempoSLA(restante);

    if (rowEl && (status === "arrival" || status === "arrival_scheduled")) {
        rowEl.classList.toggle("linha-atrasada", restante < 0);
    }

    timers[`sla-${id}`] = setInterval(() => {
        restante -= 1;
        el.innerText = formatarTempoSLA(restante);

        if (rowEl && (status === "arrival" || status === "arrival_scheduled")) {
            rowEl.classList.toggle("linha-atrasada", restante < 0);
        }
    }, 1000);
}

// =====================================================
// 🎯 TEMPO (ARRIVAL SLA / CHECKIN / CLOSED)
// =====================================================
function formatarTempoFinal(carga) {

    // CLOSED -> tempo total
    if (carga.status === "closed" && typeof carga.tempo_total_segundos === "number") {
        return formatarSegundos(carga.tempo_total_segundos);
    }

    // CHECKIN -> começa 00:00:00 e cronômetro roda
    if (carga.status === "checkin") {
        return "00:00:00";
    }

    // ARRIVAL / ARRIVAL_SCHEDULED -> SLA vindo do backend (tempo_sla_segundos)
    // Em ARRIVAL_SCHEDULED o backend só preenche após passar do expected.
    if (carga.status === "arrival" || carga.status === "arrival_scheduled") {
        return formatarTempoSLA(carga.tempo_sla_segundos);
    }

    return "-";
}

function formatarTempoSLA(segundos) {
    if (segundos === null || segundos === undefined) return "-";
    if (typeof segundos !== "number") return "-";

    const neg = segundos < 0;
    const abs = Math.abs(segundos);

    const h = String(Math.floor(abs / 3600)).padStart(2, "0");
    const m = String(Math.floor((abs % 3600) / 60)).padStart(2, "0");
    const s = String(abs % 60).padStart(2, "0");

    return (neg ? "-" : "") + `${h}:${m}:${s}`;
}

function formatarSegundos(total) {
    const t = Number(total ?? 0);
    const horas = String(Math.floor(t / 3600)).padStart(2, "0");
    const minutos = String(Math.floor((t % 3600) / 60)).padStart(2, "0");
    const segundos = String(t % 60).padStart(2, "0");
    return `${horas}:${minutos}:${segundos}`;
}

// =====================================================
// 🔘 AÇÕES / BOTÕES
// =====================================================
function renderizarBotaoAcao(carga) {

    // ARRIVAL_SCHEDULED -> botão CARGA CHEGOU (vira ARRIVAL e inicia SLA)
    if (carga.status === "arrival_scheduled") {
        return `
            <button class="btn-acao" onclick="cargaChegou('${carga.id}')">CARGA CHEGOU</button>
            <button class="btn-delete" onclick="abrirModalDelete('${carga.id}')">Deletar</button>
        `;
    }

    // ARRIVAL -> botão Setar AA
    if (carga.status === "arrival") {
        return `
            <button class="btn-acao" onclick="abrirModalAA('${carga.id}')">Setar AA</button>
            <button class="btn-delete" onclick="abrirModalDelete('${carga.id}')">Deletar</button>
        `;
    }

    // CHECKIN -> Finalizar
    if (carga.status === "checkin") {
        return `
            <button class="btn-acao" onclick="finalizar('${carga.id}')">Finalizar</button>
            <button class="btn-delete" onclick="abrirModalDelete('${carga.id}')">Deletar</button>
        `;
    }

    if (carga.status === "closed") return "Concluída";
    if (carga.status === "no_show") return `<span class="status-no-show">No Show</span>`;
    if (carga.status === "deleted") return `<span class="status-deleted">Deletada</span>`;

    return "-";
}

// ARRIVAL_SCHEDULED -> ARRIVAL
function cargaChegou(cargaId) {
    fetch(`/pc/carga-chegou/${cargaId}`, { method: "POST" })
        .then(res => res.json())
        .then(() => carregarCargas())
        .catch(err => {
            console.error("Erro ao marcar CARGA CHEGOU:", err);
            alert("Erro ao marcar CARGA CHEGOU.");
        });
}

// =====================================================
// ✅ MODAL SETAR AA (AA DISPONÍVEIS)
// =====================================================
let cargaSelecionada = null;

function abrirModalAA(cargaId) {
    cargaSelecionada = cargaId;

    fetch("/pc/aa-disponiveis")
        .then(res => res.json())
        .then(lista => {

            if (!Array.isArray(lista) || lista.length === 0) {
                alert("Nenhum AA disponível em DOCA IN");
                return;
            }

            const container = document.getElementById("listaAA");
            const modal = document.getElementById("modalAA");
            const input = document.getElementById("inputLoginAA");

            if (!container || !modal || !input) {
                console.error("Modal AA incompleto no DOM. Precisa de #listaAA, #modalAA, #inputLoginAA");
                return;
            }

            container.innerHTML = "";
            lista.forEach(aa => {
                const item = document.createElement("div");
                item.classList.add("item-aa");
                item.innerText = `${aa.nome} (${aa.login})`;

                item.onclick = () => {
                    input.value = aa.login;
                };

                container.appendChild(item);
            });

            modal.style.display = "flex";
        })
        .catch(err => {
            console.error("Erro ao buscar AAs:", err);
            alert("Erro ao buscar AAs.");
        });
}

function fecharModalAA() {
    cargaSelecionada = null;
    const input = document.getElementById("inputLoginAA");
    const modal = document.getElementById("modalAA");
    if (input) input.value = "";
    if (modal) modal.style.display = "none";
}

function confirmarAA() {
    const input = document.getElementById("inputLoginAA");
    const login = (input?.value || "").trim();

    if (!login) {
        alert("Selecione um AA.");
        return;
    }

    fetch(`/pc/checkin/${cargaSelecionada}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ aa_responsavel: login })
    })
        .then(res => res.json())
        .then(resp => {
            if (resp?.error) {
                alert(resp.error);
                return;
            }
            fecharModalAA();
            carregarCargas();
        })
        .catch(err => {
            console.error("Erro no checkin:", err);
            alert("Erro ao setar AA.");
        });
}

// =====================================================
// ✅ FINALIZAR
// =====================================================
function finalizar(cargaId) {
    if (!confirm("Deseja finalizar esta carga?")) return;

    fetch(`/pc/finalizar/${cargaId}`, { method: "POST" })
        .then(res => res.json())
        .then(resp => {
            if (resp?.error) alert(resp.error);
            carregarCargas();
        })
        .catch(err => {
            console.error("Erro ao finalizar:", err);
            alert("Erro ao finalizar.");
        });
}

// =====================================================
// 🗑 DELETE (MODAL)
// =====================================================
let cargaDeleteSelecionada = null;

function abrirModalDelete(cargaId) {
    cargaDeleteSelecionada = cargaId;

    const modal = document.getElementById("modalDelete");
    const motivo = document.getElementById("motivoDelete");

    if (!modal || !motivo) {
        console.error("Modal delete não existe no DOM (#modalDelete, #motivoDelete)");
        return;
    }

    motivo.value = "";
    modal.style.display = "flex";
}

function fecharModalDelete() {
    cargaDeleteSelecionada = null;
    const modal = document.getElementById("modalDelete");
    if (modal) modal.style.display = "none";
}

function confirmarDelete() {
    const motivoEl = document.getElementById("motivoDelete");
    const motivo = (motivoEl?.value || "").trim();

    if (!motivo) {
        alert("Informe o motivo da exclusão.");
        return;
    }

    fetch(`/pc/deletar/${cargaDeleteSelecionada}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ motivo })
    })
        .then(res => res.json())
        .then(resp => {
            if (resp?.error) {
                alert(resp.error);
                return;
            }
            fecharModalDelete();
            carregarCargas();
        })
        .catch(err => {
            console.error("Erro ao deletar:", err);
            alert("Erro ao deletar carga.");
        });
}

// =====================================================
// 📅 FORMATAR DATA
// =====================================================
function formatarData(data) {
    if (!data) return "-";
    const d = new Date(data);
    if (isNaN(d)) return "-";

    return d.toLocaleString("pt-BR", {
        timeZone: "America/Sao_Paulo",
        hour12: false
    });
}

function renderAppointmentLink(appointmentId) {
    const id = (appointmentId ?? "").toString().trim();
    if (!id) return "-";

    const href = `https://dockmaster.na.aftx.amazonoperations.app/pt_BR/#/dockmaster/appointment/GIG2/view/${encodeURIComponent(id)}/appointmentDetail`;
    return `<a class="appointment-link" href="${href}" target="_blank" rel="noopener noreferrer">${id}</a>`;
}

function dataParaComparacao(data) {
    // Converte para YYYY-MM-DD no fuso da operação (BRT)
    const partes = new Intl.DateTimeFormat("en-CA", {
        timeZone: "America/Sao_Paulo",
        year: "numeric",
        month: "2-digit",
        day: "2-digit"
    }).formatToParts(data);

    const y = partes.find(p => p.type === "year")?.value;
    const m = partes.find(p => p.type === "month")?.value;
    const d = partes.find(p => p.type === "day")?.value;

    if (!y || !m || !d) return "";
    return `${y}-${m}-${d}`;
}

// =====================================================
// 🧾 STATUS LABEL
// =====================================================
function formatarStatusLabel(status) {
    const s = (status || "").toString().toLowerCase();

    if (s === "arrival_scheduled") return "arrival_scheduled";
    if (s === "arrival") return "arrival";
    if (s === "checkin") return "checkin";
    if (s === "closed") return "closed";
    if (s === "no_show") return "no_show";
    if (s === "deleted") return "deleted";

    return status ?? "-";
}

// =====================================================
// 🎚 FILTROS
// =====================================================
function aplicarFiltros() {
    const dataInicio = document.getElementById("filtroDataInicio")?.value;
    const dataFim = document.getElementById("filtroDataFim")?.value;
    const appointment = (document.getElementById("filtroAppointment")?.value || "").toLowerCase();

    const select = document.getElementById("filtroStatus");
    const statusSelecionados = select
        ? Array.from(select.selectedOptions).map(option => option.value)
        : [];

    const filtradas = cargasGlobais.filter(carga => {

        // STATUS
        if (statusSelecionados.length > 0 && !statusSelecionados.includes(carga.status)) {
            return false;
        }

        // DATA
        if ((dataInicio || dataFim) && carga.expected_arrival_date) {
            const dataCarga = new Date(carga.expected_arrival_date);
            if (isNaN(dataCarga)) return false;

            const dataString = dataParaComparacao(dataCarga);
            if (dataInicio && dataString < dataInicio) return false;
            if (dataFim && dataString > dataFim) return false;
        }

        // APPOINTMENT
        if (appointment) {
            const id = (carga.appointment_id ?? "").toString().toLowerCase();
            if (!id.includes(appointment)) return false;
        }

        return true;
    });

    renderizarTabela(filtradas);
}

function limparFiltros() {
    const dataInicio = document.getElementById("filtroDataInicio");
    const dataFim = document.getElementById("filtroDataFim");
    const appointment = document.getElementById("filtroAppointment");
    const select = document.getElementById("filtroStatus");

    if (dataInicio) dataInicio.value = "";
    if (dataFim) dataFim.value = "";
    if (appointment) appointment.value = "";

    if (select) {
        Array.from(select.options).forEach(option => option.selected = false);
    }

    renderizarTabela(cargasGlobais);
}

// =====================================================
// 📊 PRIORIDADE
// =====================================================
function calcularPrioridade(score) {
    if (score >= 80) return { label: "Alta", classe: "prio-alta" };
    if (score >= 50) return { label: "Média", classe: "prio-media" };
    return { label: "Baixa", classe: "prio-baixa" };
}

// =====================================================
// 🗑 LIMPAR BANCO
// =====================================================
function limparBanco() {
    const confirmacao = confirm(
        "⚠ ATENÇÃO!\n\nIsso irá apagar TODAS as cargas do banco.\n\nDeseja continuar?"
    );

    if (!confirmacao) return;

    fetch("/pc/limpar-banco", { method: "DELETE" })
        .then(res => res.json())
        .then(data => {
            alert(`${data.deletadas} cargas removidas.`);
            carregarCargas();
        })
        .catch(err => {
            console.error("Erro ao limpar banco:", err);
            alert("Erro ao limpar banco.");
        });
}

// =====================================================
// 📄 EOS (se existir no seu DOM)
// =====================================================
function abrirModalEOS() {
    const modal = document.getElementById("modalEOS");
    if (modal) modal.style.display = "block";
}

document.getElementById("formEOS")?.addEventListener("submit", async function (e) {
    e.preventDefault();

    const formData = new FormData(this);

    const response = await fetch("/dashboard/fechar-turno", {
        method: "POST",
        body: formData
    });

    if (!response.ok) {
        alert("Erro ao gerar EOS");
        return;
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = `EOS_DOCA_${new Date().toISOString().split("T")[0]}.xlsx`;
    a.click();
});