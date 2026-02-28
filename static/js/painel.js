document.addEventListener("DOMContentLoaded", () => {
    carregarCargas();
});

let timers = {};
let cargasGlobais = [];

/* =====================================================
   🔄 CARREGAR CARGAS
===================================================== */
function carregarCargas() {
    fetch("/pc/listar")
        .then(res => res.json())
        .then(data => {
            cargasGlobais = data;
            renderizarTabela(data);
        })
        .catch(err => console.error("Erro ao carregar cargas:", err));
}

/* =====================================================
   🧱 RENDERIZAR TABELA
===================================================== */
function renderizarTabela(cargas) {

    // Limpa timers antigos
    Object.values(timers).forEach(clearInterval);
    timers = {};

    const tabela = document.getElementById("tabelaCargas");
    tabela.innerHTML = "";

    cargas.forEach(carga => {

        const tr = document.createElement("tr");
        const prioridade = calcularPrioridade(carga.priority_score ?? 0);

        tr.innerHTML = `
            <td>${carga.appointment_id ?? "-"}</td>
            <td>${carga.truck_tipo ?? "-"}</td>
            <td>${formatarData(carga.expected_arrival_date)}</td>
            <td>${carga.units ?? 0}</td>
            <td>${carga.cartons ?? 0}</td>
            <td>${carga.status}</td>
            <td>${carga.aa_responsavel ?? "-"}</td>
            <td>
                <span class="${prioridade.classe}">
                    ${carga.priority_score ?? 0} (${prioridade.label})
                </span>
            </td>
            <td id="timer-${carga.id}">
                ${formatarTempoFinal(carga)}
            </td>
            <td>${renderizarBotaoAcao(carga)}</td>
        `;

        tabela.appendChild(tr);

        // Iniciar cronômetro apenas se estiver em checkin
        if (carga.status === "checkin" && carga.start_time) {
            iniciarCronometro(carga.id, carga.start_time);
        }
    });
}

/* =====================================================
   ⏱ CRONÔMETRO
===================================================== */
function iniciarCronometro(id, startTimeISO) {

    const start = new Date(startTimeISO);

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
    if (el) {
        el.innerText = `${horas}:${minutos}:${segundos}`;
    }
}

/* =====================================================
   🎯 FORMATAR TEMPO FINAL
===================================================== */
function formatarTempoFinal(carga) {

    if (carga.status === "closed" && carga.tempo_total_segundos) {
        return formatarSegundos(carga.tempo_total_segundos);
    }

    if (carga.status === "checkin") {
        return "00:00:00";
    }

    return "-";
}

function formatarSegundos(total) {

    const horas = String(Math.floor(total / 3600)).padStart(2, "0");
    const minutos = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
    const segundos = String(total % 60).padStart(2, "0");

    return `${horas}:${minutos}:${segundos}`;
}

/* =====================================================
   🔘 BOTÕES
===================================================== */
function renderizarBotaoAcao(carga) {

    if (carga.status === "arrival") {
        return `<button class="btn-acao" onclick="checkin('${carga.id}')">Setar AA</button>`;
    }

    if (carga.status === "checkin") {
        return `<button class="btn-acao" onclick="finalizar('${carga.id}')">Finalizar</button>`;
    }

    if (carga.status === "closed") {
        return "Concluída";
    }

    if (carga.status === "no_show") {
    return '<span class="status-no-show">No Show</span>';
}

    return "-";
}

/* =====================================================
   🚀 CHECKIN
===================================================== */
function checkin(cargaId) {

    fetch("/pc/aa-disponiveis")
        .then(res => res.json())
        .then(lista => {

            if (lista.length === 0) {
                alert("Nenhum AA disponível em DOCA IN");
                return;
            }

            let options = lista.map(aa =>
                `<option value="${aa.badge}">
                    ${aa.nome} (${aa.badge})
                </option>`
            ).join("");

            const selectHTML = `
                <select id="selectAA">
                    ${options}
                </select>
            `;

            const escolha = prompt(
                "Digite o badge do AA disponível:\n\n" +
                lista.map(a => `${a.nome} - ${a.badge}`).join("\n")
            );

            if (!escolha) return;

            fetch(`/pc/checkin/${cargaId}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ aa_responsavel: escolha })
            })
            .then(() => carregarCargas());

        });
}

fetch("/pc/aa-disponiveis")
    .then(res => {
        if (!res.ok) {
            throw new Error("Erro ao buscar AAs");
        }
        return res.json();
    })
    .then(lista => {

        if (!Array.isArray(lista)) {
            console.error("Resposta inesperada:", lista);
            return;
        }

        lista.forEach(aa => {
            console.log(aa);
        });

    })
    .catch(err => console.error(err));



/* =====================================================
   ✅ FINALIZAR
===================================================== */
function finalizar(cargaId) {

    if (!confirm("Deseja finalizar esta carga?")) return;

    fetch(`/pc/finalizar/${cargaId}`, {
        method: "POST"
    })
    .then(() => carregarCargas());
}

/* =====================================================
   📅 FORMATAR DATA
===================================================== */
function formatarData(data) {
    if (!data) return "-";
    const d = new Date(data);
    return isNaN(d) ? "-" : d.toLocaleString("pt-BR");
}

/* =====================================================
   🎚 FILTROS
===================================================== */
function aplicarFiltros() {

    const dataInicio = document.getElementById("filtroDataInicio")?.value;
    const dataFim = document.getElementById("filtroDataFim")?.value;
    const appointment = document.getElementById("filtroAppointment")?.value.toLowerCase() || "";

    const select = document.getElementById("filtroStatus");
    const statusSelecionados = select
        ? Array.from(select.selectedOptions).map(option => option.value)
        : [];

    const filtradas = cargasGlobais.filter(carga => {

        // STATUS
        if (statusSelecionados.length > 0 && !statusSelecionados.includes(carga.status)) {
            return false;
        }

        // DATA (sem bug de timezone)
        if ((dataInicio || dataFim) && carga.expected_arrival_date) {

            const dataCarga = new Date(carga.expected_arrival_date);
            if (isNaN(dataCarga)) return false;

            const dataString = dataCarga.toISOString().split("T")[0];

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

/* =====================================================
   📊 PRIORIDADE
===================================================== */
function calcularPrioridade(score) {

    if (score >= 80) {
        return { label: "Alta", classe: "prio-alta" };
    }

    if (score >= 50) {
        return { label: "Média", classe: "prio-media" };
    }

    return { label: "Baixa", classe: "prio-baixa" };
}

/* =====================================================
   🗑 LIMPAR BANCO
===================================================== */
function limparBanco() {

    const confirmacao = confirm(
        "⚠ ATENÇÃO!\n\nIsso irá apagar TODAS as cargas do banco.\n\nDeseja continuar?"
    );

    if (!confirmacao) return;

    fetch("/pc/limpar-banco", {
        method: "DELETE"
    })
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
function renderizarBotaoAcao(carga) {

    if (carga.status === "arrival") {
        return `
            <button class="btn-acao" onclick="checkin('${carga.id}')">Setar AA</button>
            <button class="btn-delete" onclick="abrirModalDelete('${carga.id}')">Deletar</button>
        `;
    }

    if (carga.status === "checkin") {
        return `
            <button class="btn-acao" onclick="finalizar('${carga.id}')">Finalizar</button>
            <button class="btn-delete" onclick="abrirModalDelete('${carga.id}')">Deletar</button>
        `;
    }

    if (carga.status === "closed") {
        return "Concluída";
    }

    if (carga.status === "deleted") {
        return `<span class="status-deleted">Deletada</span>`;
    }

    return "-";
}



let cargaDeleteSelecionada = null;

window.abrirModalDelete = function(cargaId) {
    cargaDeleteSelecionada = cargaId;
    document.getElementById("motivoDelete").value = "";
    document.getElementById("modalDelete").style.display = "flex";
};

window.fecharModalDelete = function() {
    cargaDeleteSelecionada = null;
    document.getElementById("modalDelete").style.display = "none";
};

window.confirmarDelete = function() {

    const motivo = document.getElementById("motivoDelete").value;

    if (!motivo.trim()) {
        alert("Informe o motivo da exclusão.");
        return;
    }

    fetch(`/pc/deletar/${cargaDeleteSelecionada}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ motivo })
    })
    .then(res => res.json())
    .then(() => {
        fecharModalDelete();
        carregarCargas();
    })
    .catch(err => {
        console.error("Erro ao deletar:", err);
        alert("Erro ao deletar carga.");
    });
};

let cargaSelecionada = null;

function checkin(cargaId) {

    cargaSelecionada = cargaId;

    fetch("/pc/aa-disponiveis")
        .then(res => res.json())
        .then(lista => {

            const container = document.getElementById("listaAA");

            if (!container) {
                console.error("Elemento listaAA não encontrado no DOM");
                return;
            }

            container.innerHTML = "";

            lista.forEach(aa => {
                const item = document.createElement("div");
                item.classList.add("item-aa");
                item.innerText = `${aa.nome} (${aa.login})`;

                item.onclick = () => {
                    document.getElementById("inputLoginAA").value = aa.login;
                };

                container.appendChild(item);
            });

            document.getElementById("modalAA").style.display = "flex";
        });
}

function fecharModalAA(){
    cargaSelecionada = null;
    document.getElementById("inputLoginAA").value = "";
    document.getElementById("modalAA").style.display = "none";
}

function confirmarAA(){

    const login = document.getElementById("inputLoginAA").value;

    if (!login){
        alert("Selecione um AA.");
        return;
    }

    fetch(`/pc/checkin/${cargaSelecionada}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ aa_responsavel: login })
    })
    .then(() => {
        fecharModalAA();
        carregarCargas();
    });
}


function abrirModalEOS() {
    document.getElementById("modalEOS").style.display = "block";
}

document.getElementById("formEOS").addEventListener("submit", async function(e) {
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

