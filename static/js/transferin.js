let transferenciaSelecionada = null;
let transferenciaAppointmentSelecionada = "";
let timersTransfer = {};

document.addEventListener("DOMContentLoaded", () => {
    carregarTransferencias();
});

function carregarTransferencias() {
    Object.values(timersTransfer).forEach(clearInterval);
    timersTransfer = {};

    const appointment = document.getElementById("filtroTransferAppointment")?.value || "";
    const origem = document.getElementById("filtroTransferOrigem")?.value || "";
    const status = document.getElementById("filtroTransferStatus")?.value || "";

    const params = new URLSearchParams({ appointment, origem, status });

    fetch(`/transferin/listar?${params.toString()}`)
        .then(r => r.json())
        .then(renderizarTransferencias)
        .catch(err => {
            console.error(err);
            alert("Erro ao carregar transferências.");
        });
}

function renderizarTransferencias(lista) {
    const tbody = document.getElementById("tabelaTransferencias");
    if (!tbody) return;

    tbody.innerHTML = "";

    if (!Array.isArray(lista) || lista.length === 0) {
        tbody.innerHTML = `<tr><td colspan="11" class="linha-sem-dados">Nenhuma transferência do dia encontrada.</td></tr>`;
        return;
    }

    lista.forEach(t => {
        const tr = document.createElement("tr");
        const statusCard = obterStatusCard(t);

        tr.classList.add(`transfer-${statusCard}`);

        tr.innerHTML = `
            <td>${renderAppointmentLink(t.appointment_id)}</td>
            <td>${formatarData(t.expected_arrival_date)}</td>
            <td>${(t.status_carga || "-").toUpperCase()}</td>
            <td>${Number(t.units || 0)}</td>
            <td>${Number(t.cartons || 0)}</td>
            <td>${t.vrid || "-"}</td>
            <td>${t.origem || "-"}</td>
            <td>${formatarData(t.late_stow_deadline)}</td>
            <td id="timer-transfer-${t.id}">${formatarTempoPrazo(t.tempo_prazo_segundos, t.finalizada)}</td>
            <td><span class="badge-transfer badge-${statusCard}">${statusCard}</span></td>
            <td>
                <button class="btn-acao" onclick="abrirModalTransfer('${t.id ?? ""}', '${escapeJs(t.appointment_id || "")}', '${escapeJs(t.vrid || "")}', '${(t.origem || "")}', '${toDatetimeLocal(t.late_stow_deadline)}')">✏️</button>
                ${t.info_preenchida && !t.finalizada ? `<button class="btn-filtrar" onclick="finalizarTransfer('${t.id}')">Finalizar</button>` : ""}
            </td>
        `;

        tbody.appendChild(tr);

        if (!t.finalizada && typeof t.tempo_prazo_segundos === "number") {
            iniciarTimerPrazo(t.id, t.tempo_prazo_segundos);
        }
    });
}

function obterStatusCard(t) {
    if (t.finalizada) return "finalizada";
    if (t.prazo_estourado) return "atrasada";
    if (t.info_preenchida) return "preenchida";
    return "pendente";
}

function iniciarTimerPrazo(id, tempoInicialSegundos) {
    const el = document.getElementById(`timer-transfer-${id}`);
    if (!el) return;

    let restante = Number(tempoInicialSegundos);
    el.textContent = formatarTempoPrazo(restante, false);

    timersTransfer[id] = setInterval(() => {
        restante -= 1;
        el.textContent = formatarTempoPrazo(restante, false);
    }, 1000);
}

function formatarTempoPrazo(segundos, finalizada) {
    if (finalizada) return "Finalizada";
    if (segundos === null || segundos === undefined || Number.isNaN(Number(segundos))) return "-";

    const neg = Number(segundos) < 0;
    const abs = Math.abs(Number(segundos));

    const h = String(Math.floor(abs / 3600)).padStart(2, "0");
    const m = String(Math.floor((abs % 3600) / 60)).padStart(2, "0");
    const s = String(abs % 60).padStart(2, "0");

    return `${neg ? "-" : ""}${h}:${m}:${s}`;
}

function abrirModalTransfer(id, appointmentId, vrid, origem, lateStow) {
    transferenciaSelecionada = id || "";
    transferenciaAppointmentSelecionada = appointmentId || "";
    const modal = document.getElementById("modalTransferInfo");
    if (!modal) return;

    const appointmentEl = document.getElementById("transferAppointmentId");
    if (appointmentEl) appointmentEl.textContent = transferenciaAppointmentSelecionada || "-";

    document.getElementById("transferVrid").value = vrid || "";
    document.getElementById("transferOrigem").value = origem || "";
    document.getElementById("transferLateStow").value = lateStow || "";

    modal.style.display = "flex";
}

function fecharModalTransfer() {
    transferenciaSelecionada = null;
    transferenciaAppointmentSelecionada = "";
    const modal = document.getElementById("modalTransferInfo");
    if (modal) modal.style.display = "none";
}

function salvarTransferInfo() {
    const vrid = (document.getElementById("transferVrid")?.value || "").trim();
    const origem = (document.getElementById("transferOrigem")?.value || "").trim();
    const late_stow_deadline = (document.getElementById("transferLateStow")?.value || "").trim();

    const transferId = Number(transferenciaSelecionada);
    const endpointId = Number.isFinite(transferId) ? transferId : 0;

    fetch(`/transferin/atualizar/${endpointId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            vrid,
            origem,
            late_stow_deadline,
            appointment_id: transferenciaAppointmentSelecionada,
        })
    })
        .then(r => r.json())
        .then(resp => {
            if (resp?.error) {
                alert(resp.error);
                return;
            }
            fecharModalTransfer();
            carregarTransferencias();
        })
        .catch(err => {
            console.error(err);
            alert("Erro ao salvar informações da transferência.");
        });
}

function finalizarTransfer(id) {
    if (!confirm("Finalizar esta transferência?")) return;

    fetch(`/transferin/finalizar/${id}`, { method: "POST" })
        .then(r => r.json())
        .then(resp => {
            if (resp?.error) {
                alert(resp.error);
                return;
            }
            carregarTransferencias();
        })
        .catch(err => {
            console.error(err);
            alert("Erro ao finalizar transferência.");
        });
}

function limparFiltrosTransfer() {
    const a = document.getElementById("filtroTransferAppointment");
    const o = document.getElementById("filtroTransferOrigem");
    const s = document.getElementById("filtroTransferStatus");
    if (a) a.value = "";
    if (o) o.value = "";
    if (s) s.value = "";
    carregarTransferencias();
}

function formatarData(valor) {
    if (!valor) return "-";
    const d = new Date(valor);
    if (Number.isNaN(d.getTime())) return "-";
    return d.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", hour12: false });
}

function toDatetimeLocal(valor) {
    if (!valor) return "";
    const d = new Date(valor);
    if (Number.isNaN(d.getTime())) return "";

    const parts = new Intl.DateTimeFormat("sv-SE", {
        timeZone: "America/Sao_Paulo",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false
    }).format(d);

    return parts.replace(" ", "T");
}

function renderAppointmentLink(appointmentId) {
    const id = (appointmentId ?? "").toString().trim();
    if (!id) return "-";

    const href = `https://dockmaster.na.aftx.amazonoperations.app/pt_BR/#/dockmaster/appointment/GIG2/view/${encodeURIComponent(id)}/appointmentDetail`;
    return `<a class="appointment-link" href="${href}" target="_blank" rel="noopener noreferrer">${id}</a>`;
}

function escapeJs(texto) {
    return String(texto ?? "").replaceAll("\\", "\\\\").replaceAll("'", "\\'").replaceAll("\n", "\\n");
}
