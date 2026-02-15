document.addEventListener("DOMContentLoaded", () => {
    carregarCargas();
});

let timers = {};
let cargasGlobais = [];

/* ===============================
   🔄 CARREGAR CARGAS
=================================*/
function carregarCargas() {
    fetch("/pc/listar")
        .then(res => res.json())
        .then(data => {
            cargasGlobais = data;
            renderizarTabela(data);
        })
        .catch(err => console.error("Erro ao carregar cargas:", err));
}

/* ===============================
   🧱 RENDERIZAR TABELA
=================================*/
function renderizarTabela(cargas) {

    // 🔥 Limpa timers antigos
    Object.values(timers).forEach(clearInterval);
    timers = {};

    const tabela = document.getElementById("tabelaCargas");
    tabela.innerHTML = "";

    cargas.forEach(carga => {

        const tr = document.createElement("tr");

        const prioridade = calcularPrioridade(carga.priority_score);

        tr.innerHTML = `
            <td>${carga.appointment_id ?? "-"}</td>
            <td>${formatarData(carga.expected_arrival_date)}</td>
            <td>${carga.units}</td>
            <td>${carga.cartons}</td>
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

        // ⏱ Iniciar cronômetro se estiver em checkin
        if (carga.status === "checkin" && carga.start_time) {
            iniciarCronometro(carga.id, carga.start_time);
        }
    });
}

/* ===============================
   ⏱ CRONÔMETRO
=================================*/
function iniciarCronometro(id, startTimeISO) {

    const start = new Date(startTimeISO);

    timers[id] = setInterval(() => {

        const agora = new Date();
        const diff = Math.floor((agora - start) / 1000);

        atualizarTempoTela(id, diff);

    }, 1000);
}

function atualizarTempoTela(id, totalSegundos) {

    const horas = String(Math.floor(totalSegundos / 3600)).padStart(2, '0');
    const minutos = String(Math.floor((totalSegundos % 3600) / 60)).padStart(2, '0');
    const segundos = String(totalSegundos % 60).padStart(2, '0');

    const el = document.getElementById(`timer-${id}`);
    if (el) {
        el.innerText = `${horas}:${minutos}:${segundos}`;
    }
}

/* ===============================
   🎯 FORMATAR TEMPO FINAL
=================================*/
function formatarTempoFinal(carga) {

    // Se já foi finalizada
    if (carga.status === "closed" && carga.tempo_total_segundos) {
        return formatarSegundos(carga.tempo_total_segundos);
    }

    // Se estiver rodando
    if (carga.status === "checkin") {
        return "00:00:00";
    }

    return "-";
}

function formatarSegundos(total) {

    const horas = String(Math.floor(total / 3600)).padStart(2, '0');
    const minutos = String(Math.floor((total % 3600) / 60)).padStart(2, '0');
    const segundos = String(total % 60).padStart(2, '0');

    return `${horas}:${minutos}:${segundos}`;
}

/* ===============================
   🔘 BOTÕES DE AÇÃO
=================================*/
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
        return "No Show";
    }

    return "-";
}

/* ===============================
   🚀 CHECKIN
=================================*/
function checkin(cargaId) {

    const aa = prompt("Digite o login do AA:");
    if (!aa) return;

    fetch(`/pc/checkin/${cargaId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ aa_responsavel: aa })
    })
    .then(() => carregarCargas());
}

/* ===============================
   ✅ FINALIZAR
=================================*/
function finalizar(cargaId) {

    if (!confirm("Deseja finalizar esta carga?")) return;

    fetch(`/pc/finalizar/${cargaId}`, {
        method: "POST"
    })
    .then(() => carregarCargas());
}

/* ===============================
   📅 FORMATAR DATA
=================================*/
function formatarData(data) {
    if (!data) return "-";
    const d = new Date(data);
    return isNaN(d) ? "-" : d.toLocaleString("pt-BR");
}

/* ===============================
   🎚 FILTROS
=================================*/
function aplicarFiltros() {

    const dataInicio = document.getElementById("filtroDataInicio")?.value;
    const dataFim = document.getElementById("filtroDataFim")?.value;
    const appointment = document.getElementById("filtroAppointment")?.value.toLowerCase() || "";

    const select = document.getElementById("filtroStatus");
    const statusSelecionados = select
        ? Array.from(select.selectedOptions).map(option => option.value)
        : [];

    const filtradas = cargasGlobais.filter(carga => {

        let passaStatus = true;
        let passaData = true;
        let passaAppointment = true;

        // 🔹 FILTRO STATUS MULTIPLO
        if (statusSelecionados.length > 0) {
            passaStatus = statusSelecionados.includes(carga.status);
        }

      // 🔹 FILTRO DATA (CORRIGIDO)
if ((dataInicio || dataFim) && carga.expected_arrival_date) {

    const dataCarga = new Date(carga.expected_arrival_date);

    if (isNaN(dataCarga)) return false;

    const anoCarga = dataCarga.getFullYear();
    const mesCarga = dataCarga.getMonth();
    const diaCarga = dataCarga.getDate();

    if (dataInicio) {
        const inicio = new Date(dataInicio);
        if (
            anoCarga < inicio.getFullYear() ||
            (anoCarga === inicio.getFullYear() && mesCarga < inicio.getMonth()) ||
            (anoCarga === inicio.getFullYear() && mesCarga === inicio.getMonth() && diaCarga < inicio.getDate()) -1
        ) {
            return false;
        }
    }

    if (dataFim) {
        const fim = new Date(dataFim);
        if (
            anoCarga > fim.getFullYear() ||
            (anoCarga === fim.getFullYear() && mesCarga > fim.getMonth()) ||
            (anoCarga === fim.getFullYear() && mesCarga === fim.getMonth() && diaCarga > fim.getDate())-1
        ) {
            return false;
        }
    }
}
  

        // 🔹 FILTRO APPOINTMENT
        if (appointment) {
            passaAppointment = (carga.appointment_id ?? "")
                .toString()
                .toLowerCase()
                .includes(appointment);
        }

        return passaStatus && passaData && passaAppointment;
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


/* ===============================
   📊 PRIORIDADE
=================================*/
function calcularPrioridade(score) {

    if (score >= 80) {
        return { label: "Alta", classe: "prio-alta" };
    }

    if (score >= 50) {
        return { label: "Média", classe: "prio-media" };
    }

    return { label: "Baixa", classe: "prio-baixa" };
}
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
