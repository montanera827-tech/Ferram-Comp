const API = "http://127.0.0.1:8000"

let historico = []
let token = localStorage.getItem("token")

// ===== PROTEÇÃO CONTRA ERROS =====
// Captura erros não tratados
window.addEventListener("error", function(event) {
    console.error("Erro capturado:", event.message)
    // Evita que o navegador faça refresh automático
    event.preventDefault()
})

// Captura rejeições de promises não tratadas
window.addEventListener("unhandledrejection", function(event) {
    console.error("Promise rejeitada:", event.reason)
    event.preventDefault()
})



// Adiciona suporte a Enter no campo de chat
document.addEventListener("DOMContentLoaded", function() {
    const perguntaInput = document.getElementById("pergunta")
    if(perguntaInput) {
        perguntaInput.addEventListener("keypress", function(event) {
            if(event.key === "Enter") {
                event.preventDefault()
                chat()
            }
        })
    }
})

// ENTRAR
function entrarSistema(){
    try {
        document.getElementById("loginScreen").style.display = "none"
        document.querySelector(".container").style.display = "flex"
    } catch(e) {
        console.error("Erro ao entrar:", e)
    }
}
// ===== ENTRAR SEM LOGIN =====
function entrarSemLogin(){

    // cria token fake temporário
    token = "visitante"

    // salva localmente
    localStorage.setItem("token", token)

    // entra no sistema
    entrarSistema()

    // mensagem inicial
    document.getElementById("mensagens").innerHTML += `
        <div class="msg ia">
            👋 Bem-vindo visitante!
        </div>
    `
}
async function cadastrar(){
    const email = document.getElementById("email").value
    const senha = document.getElementById("senha").value

    const res = await fetch(API + "/register", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            email: email,
            password: senha,
            role: "aluno"
        })
    })

    const data = await res.json()
    alert(data.msg || data.erro)
}

async function login(){
    const email = document.getElementById("email").value
    const senha = document.getElementById("senha").value

    const res = await fetch(API + "/login", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            email: email,
            password: senha
        })
    })

    const data = await res.json()

    if(data.access_token){
        token = data.access_token
        localStorage.setItem("token", token)
        entrarSistema()
    }else{
        alert(data.erro || "Erro ao entrar")
    }
}

// SAIR
function logout(){
    localStorage.removeItem("token")
    token = null
    location.reload()
}

// ===== VTUBER =====
function setAvatar(state){
    const avatar = document.getElementById("avatar")

    avatar.classList.remove("avatar-idle","avatar-thinking","avatar-speaking")

    if(state === "idle"){
        avatar.src = "imagens/idle.gif"
    }

    if(state === "thinking"){
        avatar.src = "imagens/thinking.gif"
    }

    if(state === "speaking"){
        avatar.src = "imagens/speaking.gif"
    }
}

// ===== CHAT (SÓ AQUI FOI AJUSTADO) =====
let chatEmProgresso = false

async function chat(){
    if(chatEmProgresso) return // Evita múltiplos cliques
    
    const msgBox = document.getElementById("mensagens")
    const perguntaInput = document.getElementById("pergunta")
    const codigoInput = document.getElementById("codigo")

    let pergunta = perguntaInput.value?.trim()
    if(!pergunta) return

    try {
        chatEmProgresso = true
        
        msgBox.innerHTML += `<div class="msg user">🧑 ${pergunta}</div>`
        perguntaInput.value = ""

        setAvatar("thinking")

        // 🔥 adiciona no histórico
        historico.push({
            role: "user",
            content: pergunta
        })

        const res = await fetch(API+"/chat",{
            method:"POST",
            headers:{
    "Content-Type":"application/json",
    ...(token && token !== "visitante"
        ? { "Authorization": "Bearer " + token }
        : {})
},
            body:JSON.stringify({
                pergunta: pergunta,
                codigo: codigoInput.value,
                historico: historico
            })
        })

        if(!res.ok) {
            throw new Error("Erro na resposta do servidor")
        }

        const data = await res.json()

        if(data.erro) {
            msgBox.innerHTML += `<div class="msg ia">❌ ${data.erro}</div>`
            setAvatar("idle")
            return
        }

        msgBox.innerHTML += `<div class="msg ia">🤖 ${data.resposta}</div>`

        // 🔥 salva resposta da IA
        historico.push({
            role: "assistant",
            content: data.resposta
        })

        falar(data.resposta)

    }catch(e){
        console.error("Erro no chat:", e)
        msgBox.innerHTML += `<div class="msg ia">❌ Erro ao conectar</div>`
        setAvatar("idle")
    } finally {
        chatEmProgresso = false
        msgBox.scrollTop = msgBox.scrollHeight
    }
}

// ===== FALA =====
function falar(texto){

    speechSynthesis.cancel()

    setAvatar("speaking")

    const speech = new SpeechSynthesisUtterance(texto)  

    speech.lang = "pt-BR"

    speech.rate = 1.9

    speech.pitch = 1.6

    const voices = speechSynthesis.getVoices()

    let voz = voices.find(v => v.lang.includes("pt"))

    if(voz){
        speech.voice = voz
    }

    speech.onend = () => {
        setAvatar("idle")
    }

    speechSynthesis.speak(speech)
}
// ===== COMPILADOR =====
let runEmProgresso = false

async function run(){
    if(runEmProgresso) return // Evita múltiplos cliques
    
    const codigo = document.getElementById("codigo").value
    const saida = document.getElementById("saida")

    try {
        runEmProgresso = true
        saida.innerText = "Compilando..."

        const res = await fetch(API + "/run", {
            method: "POST",
            headers:{
                "Content-Type":"application/json"
            },
            body: JSON.stringify({
                codigo: codigo
            })
        })

        if(!res.ok) {
            throw new Error("Erro na resposta do servidor")
        }

        const data = await res.json()

        if(data.status === "roda"){
            saida.innerText = data.terminal
        }else{
            saida.innerText = "❌ " + data.terminal
        }

    }catch(e){
        console.error("Erro ao compilar:", e)
        saida.innerText = "❌ Erro ao conectar com compilador"
    } finally {
        runEmProgresso = false
    }
}
async function abrirAulas(){
    const area = document.getElementById("aulas")
    const chat = document.querySelector(".bottom-half")

    try {
        chat.style.display = "none"
        area.style.display = "block"

        area.innerHTML = "Carregando aulas..."

        const res = await fetch(API + "/lessons")
        
        if(!res.ok) {
            throw new Error("Erro ao carregar aulas")
        }

        const aulas = await res.json()

        area.innerHTML = ""

        aulas.forEach(aula => {
            area.innerHTML += `
                <div class="msg ia" onclick="abrirAula(${aula.id})">
                    ${aula.emoji} <b>${aula.title}</b><br>
                    ${aula.description}
                </div>
            `
        })

    }catch(e){
        console.error("Erro ao abrir aulas:", e)
        area.innerHTML = "❌ Erro ao carregar aulas"
    }
}
async function abrirAula(id){
    const area = document.getElementById("aulas")
    const msgBox = document.getElementById("mensagens")

    try{
        const res = await fetch(API + "/lesson/" + id)
        const aula = await res.json()

        // coloca código no editor
        document.getElementById("codigo").value = aula.starter_code || ""

        abrirChat()

        // mostra carregando
        msgBox.innerHTML += `<div class="msg ia">📚 Explicando aula...</div>`

        // 🔥 chama IA
        const resIA = await fetch(API + "/explicar_aula", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                titulo: aula.title,
                descricao: aula.description
            })
        })

        const data = await resIA.json()

        // remove "explicando"
        msgBox.innerHTML = msgBox.innerHTML.replace("📚 Explicando aula...", "")

        // mostra explicação
        msgBox.innerHTML += `
            <div class="msg ia">
                📚 <b>${aula.title}</b><br>
                ${data.explicacao}
            </div>
        `

        // 🔊 fala a explicação
        falar(data.explicacao)

    }catch(e){
        area.innerHTML = "Erro ao abrir aula"
        console.log(e)
    }

    msgBox.scrollTop = msgBox.scrollHeight
}
function abrirChat(){
    document.getElementById("aulas").style.display = "none"
    document.querySelector(".bottom-half").style.display = "flex"
}

let corrigindoEmProgresso = false

async function corrigirCodigo(){
    if(corrigindoEmProgresso) return // Evita múltiplos cliques
    
    const codigoInput = document.getElementById("codigo")
    const entrada = document.getElementById("entrada").value
    const saida = document.getElementById("saida").innerText
    const msgBox = document.getElementById("mensagens")

    try {
        corrigindoEmProgresso = true
        msgBox.innerHTML += `<div class="msg ia">🧠 Corrigindo código...</div>`

        const res = await fetch(API + "/enviar_resposta", {
            method: "POST",
            headers: {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token
            },
            body: JSON.stringify({
                codigo: codigoInput.value,
                entrada: entrada,
                saida: saida,
                esperado: ""
            })
        })

        if(!res.ok) {
            throw new Error("Erro ao corrigir código")
        }

        const data = await res.json()

        msgBox.innerHTML += `<div class="msg ia">📊 ${data.feedback || data.erro}</div>`

        falar(data.feedback || data.erro)

    }catch(e){
        console.error("Erro ao corrigir:", e)
        msgBox.innerHTML += `<div class="msg ia">❌ Erro ao corrigir</div>`
    } finally {
        corrigindoEmProgresso = false
    }
}

function abrirGuia(){

    alert(`
GUIA DO SISTEMA

💬 Chat com IA
📚 Lições de programação
▶️ Compilar código C++
🧠 Corrigir código
🔊 Assistente com voz
👤 Entrar sem login

A Cinty esta em desemvolvimento ainda algumas funcionalidades n funcionam ainda, como cin, srand(time(0)),e funções.
    `)

}
