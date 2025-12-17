// Determine API URL dynamically based on environment
const API_URL = "https://nexus-ai-loan-agent.onrender.com/chat";;

let attachedFile = null;

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        attachedFile = file;
        const input = document.getElementById("user-input");
        input.value = `📎 ${file.name} attached`;
        input.placeholder = "Add a message or press send to upload...";
        const attachBtn = document.getElementById("attach-btn");
        attachBtn.style.backgroundColor = "#10b981";
    }
}

async function sendMessage(event) {
    if (event) event.preventDefault();
    const input = document.getElementById("user-input");
    const msg = input.value.trim();
    if (!msg && !attachedFile) return;

    const displayMsg = attachedFile ? `${msg}\n📎 Uploaded: ${attachedFile.name}` : msg;
    addMessage(displayMsg, "user");
    input.value = "";
    input.placeholder = "Ask about loans or upload payslip...";

    const loadingId = "loading-" + Date.now();
    addMessage("", "bot temporary", loadingId);

    try {
        let res;
        if (attachedFile) {
            const formData = new FormData();
            formData.append("message", msg || "I'm uploading my payslip for salary verification");
            formData.append("session_id", "demo_user");
            formData.append("file", attachedFile);
            res = await fetch(API_URL, { method: "POST", body: formData });
            attachedFile = null;
            document.getElementById("file-input").value = "";
            document.getElementById("attach-btn").style.backgroundColor = "";
        } else {
            res = await fetch(API_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: msg, session_id: "demo_user" })
            });
        }

        if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        const data = await res.json();
        const loadingBubble = document.getElementById(loadingId);
        if (loadingBubble) loadingBubble.remove();

        let responseText = data.response;
        if (typeof responseText === 'object') responseText = JSON.stringify(responseText);
        addMessage(responseText, "bot");
    } catch (e) {
        document.getElementById(loadingId)?.remove();
        console.error(e);
        addMessage("Error: " + e.message, "bot error");
    }
}

function addMessage(text, type, id = null) {
    const box = document.getElementById("chat");
    const messageWrapper = document.createElement("div");

    if (type.includes("temporary")) {
        messageWrapper.className = `message ${type}`;
        messageWrapper.id = id;
        messageWrapper.innerHTML = `<div class="typing-dots"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>`;
    } else {
        messageWrapper.className = `message ${type}`;
        if (id) messageWrapper.id = id;

        const bubble = document.createElement("div");
        bubble.className = "bubble";

        if (type.includes("bot")) {
            try {
                let htmlContent = typeof marked !== 'undefined' && marked.parse 
                    ? marked.parse(text) 
                    : text.replace(/\n/g, '<br>');
                const linkRegex = /(?<!href=")(https?:\/\/[^\s<]+)/g;
                const linkReplacement = `<a href="$1" target="_blank" class="download-link"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg> Open Document</a>`;
                htmlContent = htmlContent.replace(linkRegex, linkReplacement);
                bubble.innerHTML = htmlContent;
            } catch (e) {
                bubble.innerText = text;
            }
        } else {
            bubble.innerText = text;
        }

        messageWrapper.appendChild(bubble);
    }

    box.appendChild(messageWrapper);
    box.scrollTop = box.scrollHeight;
}

function handleEnter(e) { 
    if (e.key === "Enter") {
        e.preventDefault();
        sendMessage();
    }
}
