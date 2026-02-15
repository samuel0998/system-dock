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
        document.getElementById("resultado").innerHTML =
            `<p>${data.message}</p>
             <p>Cargas inseridas: ${data.inseridas}</p>
             <p>Ignoradas: ${data.ignoradas}</p>`;
    })
    .catch(error => {
        console.error(error);
        alert("Erro no upload.");
    });
}
