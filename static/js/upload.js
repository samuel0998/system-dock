function enviarPlanilha() {
    const fileInput = document.getElementById("fileInput");
    const file = fileInput.files[0];

    if (!file) {
        alert("Selecione um arquivo!");
        return;
    }

    const formData = new FormData();
    formData.append("file", file);

    fetch("/upload/processar", {
        method: "POST",
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        const erros = Array.isArray(data.erros) ? data.erros : [];
        const errosHtml = erros.length
            ? `<details><summary>Erros (${erros.length})</summary><pre>${erros.join("\n")}</pre></details>`
            : "";

        document.getElementById("resultado").innerHTML =
            `<p>${data.message}</p>
             <p>Cargas inseridas: ${data.inseridas}</p>
             <p>Cargas atualizadas: ${data.atualizadas ?? 0}</p>
             <p>Ignoradas: ${data.ignoradas}</p>
             <p>Appointments repetidos no arquivo: ${data.repetidas_no_arquivo ?? 0}</p>
             ${data.observacao ? `<p><strong>Obs.:</strong> ${data.observacao}</p>` : ""}
             ${errosHtml}`;
    })
    .catch(error => {
        console.error(error);
        alert("Erro no upload.");
    });
}
