// /static/js/painel.js
// Versão limpa (sem funções duplicadas) + suporte a ARRIVAL_SCHEDULED + SLA 4h em ARRIVAL
// Requisitos do backend (/pc/listar):
// - status: "arrival_scheduled" | "arrival" | "checkin" | "closed" | "no_show" | "deleted"
// - tempo_sla_segundos (number | null) para status arrival e arrival_scheduled (quando aplicável)
// - start_time (ISO | null) para status checkin
// - tempo_total_segundos (number | null) para status closed
// - truck_tipo (string | null)

document.addEventListener("DOMContentLoaded", () => {
    setarFiltrosDataHoje();
    carregarCargas();

    // Se seus botões de filtro chamam via onclick no HTML, ok.
    // Se preferir, pode ativar listeners aqui:
    // document.getElementById("btnFiltrar")?.addEventListener("click", aplicarFiltros);
    // document.getElementById("btnLimpar")?.addEventListener("click", limparFiltros);
});

let timers = {};
let cargasGlobais = [];

function can(cap) {
    return Boolean(window.AUTH_CAPS && window.AUTH_CAPS[cap]);
}

function getCargaById(cargaId) {
    return cargasGlobais.find(c => String(c.id) === String(cargaId)) || null;
}

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
            aplicarFiltros();
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
            (carga.status === "arrival" || carga.status === "arrival_scheduled" || carga.status === "checkin") &&
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
            <td id="timer-prod-${carga.id}">
                ${formatarTempoProdutivo(carga)}
            </td>
            <td id="timer-sla-${carga.id}" class="tempo-sla ${isCargaAtrasada(carga) ? "tempo-sla-atrasado" : ""}">
                ${formatarTempoSLAColuna(carga)}
            </td>
            <td>${renderizarBotaoAcao(carga)}</td>
            <td>${renderizarComentarioAtraso(carga)}</td>
        `;

        tabela.appendChild(tr);

        // Cronômetro se estiver em checkin
        if (carga.status === "checkin" && carga.start_time) {
            iniciarCronometroProdutivo(carga.id, carga.start_time);
        }

        // Timer SLA em tempo real para arrival / arrival_scheduled / checkin
        if (
            (carga.status === "arrival" || carga.status === "arrival_scheduled" || carga.status === "checkin") &&
            typeof carga.tempo_sla_segundos === "number"
        ) {
            iniciarTimerSLA(carga.id, carga.tempo_sla_segundos, carga.status);
        }
    });
}

function isCargaAtrasada(carga) {
    return (
        (carga.status === "arrival" || carga.status === "arrival_scheduled" || carga.status === "checkin") &&
        typeof carga.tempo_sla_segundos === "number" &&
        carga.tempo_sla_segundos < 0
    );
}

function renderizarComentarioAtraso(carga) {
    if (!can("painel_comment")) return "-";
    if (!isCargaAtrasada(carga)) return "-";

    const textoBotao = carga.atraso_comentario ? "Editar comentário" : "Comentar atraso";
    const balao = carga.atraso_comentario
        ? `<button class="btn-comentario-atraso" title="${escapeHtml(carga.atraso_comentario)}" onclick="mostrarComentarioExistente('${carga.id}')">💬</button>`
        : "";

    return `${balao}<button class="btn-comentario-atraso" onclick="abrirModalAtraso('${carga.id}')">${textoBotao}</button>`;
}

// 


// ⏱ CRONÔMETRO (CHECKIN)
// 
function iniciarCronometroProdutivo(id, startTimeISO) {
    const start = new Date(startTimeISO);

    // Se data inválida, não inicia
    if (isNaN(start)) return;

    timers[id] = setInterval(() => {
        const agora = new Date();
        // checkin é cronômetro crescente, nunca regressivo
        const diff = Math.max(0, Math.floor((agora - start) / 1000));
        atualizarTempoProdutivoTela(id, diff);
    }, 1000);
}

function atualizarTempoProdutivoTela(id, totalSegundos) {
    const t = Math.max(0, Number(totalSegundos || 0));
    const horas = String(Math.floor(t / 3600)).padStart(2, "0");
    const minutos = String(Math.floor((t % 3600) / 60)).padStart(2, "0");
    const segundos = String(t % 60).padStart(2, "0");

    const el = document.getElementById(`timer-prod-${id}`);
    if (el) el.innerText = `${horas}:${minutos}:${segundos}`;
}

function iniciarTimerSLA(id, tempoInicialSegundos, status) {
    const el = document.getElementById(`timer-sla-${id}`);
    if (!el) return;

    const rowEl = document.getElementById(`row-carga-${id}`);

    let restante = Number(tempoInicialSegundos);
    el.innerText = formatarTempoSLA(restante);

    if (rowEl && (status === "arrival" || status === "arrival_scheduled" || status === "checkin")) {
        rowEl.classList.toggle("linha-atrasada", restante < 0);
    }
    el.classList.toggle("tempo-sla-atrasado", restante < 0);

    timers[`sla-${id}`] = setInterval(() => {
        restante -= 1;
        el.innerText = formatarTempoSLA(restante);

        if (rowEl && (status === "arrival" || status === "arrival_scheduled" || status === "checkin")) {
            rowEl.classList.toggle("linha-atrasada", restante < 0);
        }
        el.classList.toggle("tempo-sla-atrasado", restante < 0);
    }, 1000);
}

// 
// 🎯 TEMPO (ARRIVAL SLA / CHECKIN / CLOSED)
// 
function formatarTempoProdutivo(carga) {
    // CLOSED -> tempo total produtivo consolidado
    if (carga.status === "closed" && typeof carga.tempo_total_segundos === "number") {
        return formatarSegundos(carga.tempo_total_segundos);
    }

    // CHECKIN -> cronômetro produtivo crescente
    if (carga.status === "checkin") {
        return "00:00:00";
    }

    return "-";
}

function formatarTempoSLAColuna(carga) {
    // SLA deve continuar visível inclusive em CHECKIN
    if (carga.status === "arrival" || carga.status === "arrival_scheduled" || carga.status === "checkin") {
        return formatarTempoSLA(carga.tempo_sla_segundos);
    }

    if (carga.atraso_registrado && Number(carga.atraso_segundos || 0) > 0) {
        return `-${formatarSegundos(Number(carga.atraso_segundos || 0))}`;
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

// 
// 🔘 AÇÕES / BOTÕES
// 
function renderizarBotaoAcao(carga) {
    const expertBtn = can("expert_manage")
        ? `<button class="btn-comentario-atraso" onclick="expertGerenciarCarga('${carga.id}')">Expert</button>`
        : "";

    // ARRIVAL_SCHEDULED -> botão CARGA CHEGOU (vira ARRIVAL e inicia SLA)
    if (carga.status === "arrival_scheduled") {
        return `
            ${can("painel_carga_chegou") ? `<button class="btn-acao" onclick="cargaChegou('${carga.id}')">CARGA CHEGOU</button>` : "-"}
            ${can("painel_delete") ? `<button class="btn-delete" onclick="abrirModalDelete('${carga.id}')">Deletar</button>` : ""}
            ${expertBtn}
        `;
    }

    // ARRIVAL -> botão Setar AA
    if (carga.status === "arrival") {
        return `
            ${can("painel_set_aa") ? `<button class="btn-acao" onclick="abrirModalAA('${carga.id}')">Setar AA</button>` : "-"}
            ${can("painel_delete") ? `<button class="btn-delete" onclick="abrirModalDelete('${carga.id}')">Deletar</button>` : ""}
            ${expertBtn}
        `;
    }

    // CHECKIN -> Finalizar
    if (carga.status === "checkin") {
        return `
            ${can("painel_finalize") ? `<button class="btn-acao" onclick="finalizar('${carga.id}')">Finalizar</button>` : "-"}
            ${can("painel_delete") ? `<button class="btn-delete" onclick="abrirModalDelete('${carga.id}')">Deletar</button>` : ""}
            ${expertBtn}
        `;
    }

    if (carga.status === "closed") return `Concluída ${expertBtn}`;
    if (carga.status === "no_show") return `<span class="status-no-show">No Show</span>`;
    if (carga.status === "deleted") return `<span class="status-deleted">Deletada</span>`;

    return "-";
}

let expertCargaSelecionada = null;

function expertGerenciarCarga(cargaId) {
    if (!can("expert_manage")) return;

    const carga = getCargaById(cargaId);
    if (!carga) return;

    expertCargaSelecionada = cargaId;

    document.getElementById("expertAppointmentId").value = carga.appointment_id || "";
    document.getElementById("expertStatus").value = carga.status || "arrival";
    document.getElementById("expertUnits").value = Number(carga.units || 0);
    document.getElementById("expertCartons").value = Number(carga.cartons || 0);
    document.getElementById("expertAA").value = carga.aa_responsavel || "";
    document.getElementById("expertTruckTipo").value = carga.truck_tipo || "";
    document.getElementById("expertTruckType").value = carga.truck_type || "";

    const modal = document.getElementById("modalExpertCarga");
    if (modal) modal.style.display = "flex";
}

function fecharModalExpertCarga() {
    expertCargaSelecionada = null;
    const modal = document.getElementById("modalExpertCarga");
    if (modal) modal.style.display = "none";
}

function salvarEdicaoExpert() {
    if (!expertCargaSelecionada) return;

    const updates = {
        appointment_id: (document.getElementById("expertAppointmentId")?.value || "").trim(),
        status: (document.getElementById("expertStatus")?.value || "").trim(),
        units: Number(document.getElementById("expertUnits")?.value || 0),
        cartons: Number(document.getElementById("expertCartons")?.value || 0),
        aa_responsavel: (document.getElementById("expertAA")?.value || "").trim(),
        truck_tipo: (document.getElementById("expertTruckTipo")?.value || "").trim(),
        truck_type: (document.getElementById("expertTruckType")?.value || "").trim(),
    };

    fetch(`/pc/expert/manage/${expertCargaSelecionada}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "edit", updates })
    })
        .then(r => r.json())
        .then(resp => {
            if (resp?.error) return alert(resp.error);
            fecharModalExpertCarga();
            carregarCargas();
        })
        .catch(() => alert("Erro ao salvar edição expert."));
}

function deletarHardExpert() {
    if (!expertCargaSelecionada) return;
    if (!confirm("Confirma hard delete desta carga no banco?")) return;

    fetch(`/pc/expert/manage/${expertCargaSelecionada}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "hard_delete" })
    })
        .then(r => r.json())
        .then(resp => {
            if (resp?.error) return alert(resp.error);
            fecharModalExpertCarga();
            carregarCargas();
        })
        .catch(() => alert("Erro ao deletar carga."));
}



function expertGerenciarCarga(cargaId) {
    if (!can("expert_manage")) return;

    const acao = prompt("EXPERT: digite 'delete' para apagar do banco, ou 'edit' para editar campos.");
    if (!acao) return;

    if (acao.toLowerCase() === "delete") {
        if (!confirm("Confirma hard delete desta carga no banco?")) return;
        fetch(`/pc/expert/manage/${cargaId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "hard_delete" })
        })
            .then(r => r.json())
            .then(resp => {
                if (resp?.error) return alert(resp.error);
                carregarCargas();
            });
        return;
    }

    if (acao.toLowerCase() === "edit") {
        const raw = prompt("Cole JSON de atualização. Ex: {\"status\":\"arrival\",\"units\":120}");
        if (!raw) return;
        let updates;
        try {
            updates = JSON.parse(raw);
        } catch {
            alert("JSON inválido.");
            return;
        }

        fetch(`/pc/expert/manage/${cargaId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "edit", updates })
        })
            .then(r => r.json())
            .then(resp => {
                if (resp?.error) return alert(resp.error);
                carregarCargas();
            });
    }
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

let cargaAtrasoSelecionada = null;

function abrirModalAtraso(cargaId) {
    cargaAtrasoSelecionada = cargaId;

    const modal = document.getElementById("modalAtraso");
    const textarea = document.getElementById("comentarioAtraso");
    const carga = cargasGlobais.find(c => String(c.id) === String(cargaId));

    if (!modal || !textarea) return;

    textarea.value = carga?.atraso_comentario || "";
    modal.style.display = "flex";
}

function fecharModalAtraso() {
    cargaAtrasoSelecionada = null;
    const modal = document.getElementById("modalAtraso");
    if (modal) modal.style.display = "none";
}

function mostrarComentarioExistente(cargaId) {
    const carga = cargasGlobais.find(c => String(c.id) === String(cargaId));
    alert(carga?.atraso_comentario || "Sem comentário registrado.");
}

function confirmarComentarioAtraso() {
    const textarea = document.getElementById("comentarioAtraso");
    const comentario = (textarea?.value || "").trim();

    if (!comentario) {
        alert("Digite o comentário do atraso.");
        return;
    }

    fetch(`/pc/comentar-atraso/${cargaAtrasoSelecionada}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comentario })
    })
        .then(res => res.json())
        .then(resp => {
            if (resp?.error) {
                alert(resp.error);
                return;
            }
            fecharModalAtraso();
            carregarCargas();
        })
        .catch(err => {
            console.error("Erro ao salvar comentário:", err);
            alert("Erro ao salvar comentário de atraso.");
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

function escapeHtml(texto) {
    return String(texto ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll("\"", "&quot;")
        .replaceAll("'", "&#039;");
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

    setarFiltrosDataHoje();
    if (appointment) appointment.value = "";

    if (select) {
        Array.from(select.options).forEach(option => option.selected = false);
    }

    aplicarFiltros();
}

function setarFiltrosDataHoje() {
    const hoje = new Date();
    const y = hoje.getFullYear();
    const m = String(hoje.getMonth() + 1).padStart(2, "0");
    const d = String(hoje.getDate()).padStart(2, "0");
    const valor = `${y}-${m}-${d}`;

    const dataInicio = document.getElementById("filtroDataInicio");
    const dataFim = document.getElementById("filtroDataFim");

    if (dataInicio) dataInicio.value = valor;
    if (dataFim) dataFim.value = valor;
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
// ➕ ADICIONAR CARGA (LC5+)
// =====================================================
function abrirModalAdicionarCarga() {
    if (!can("painel_set_aa")) return;
    const modal = document.getElementById("modalAdicionarCarga");
    if (modal) modal.style.display = "flex";
}

function fecharModalAdicionarCarga() {
    const modal = document.getElementById("modalAdicionarCarga");
    if (modal) modal.style.display = "none";
}

function confirmarAdicionarCarga() {
    const payload = {
        appointment_id: (document.getElementById("addAppointmentId")?.value || "").trim(),
        expected_arrival_date: (document.getElementById("addExpectedArrivalDate")?.value || "").trim(),
        status: (document.getElementById("addStatus")?.value || "arrival_scheduled").trim(),
        units: Number(document.getElementById("addUnits")?.value || 0),
        cartons: Number(document.getElementById("addCartons")?.value || 0),
        truck_tipo: (document.getElementById("addTruckTipo")?.value || "").trim(),
        truck_type: (document.getElementById("addTruckType")?.value || "").trim(),
    };

    fetch("/pc/adicionar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    })
        .then(r => r.json())
        .then(resp => {
            if (resp?.error) return alert(resp.error);
            fecharModalAdicionarCarga();
            carregarCargas();
        })
        .catch(() => alert("Erro ao adicionar carga."));
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
