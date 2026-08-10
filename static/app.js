// ============================================================
// AIOps Agent 前端 —— 核心:fetch + ReadableStream 读 SSE 流
// ============================================================

// ---------- 会话管理(localStorage) ----------
let currentSessionId = null;
let sending = false;
let currentImageDataUrl = null;   // 多模态:当前待发送的图片 data URL

function loadSessions() {
    return JSON.parse(localStorage.getItem("sessions") || "[]");
}
function saveSessions(sessions) {
    localStorage.setItem("sessions", JSON.stringify(sessions));
}

// ---------- 渲染会话列表 ----------
function renderSessionList() {
    const sessions = loadSessions();
    const list = document.getElementById("sessionList");
    list.innerHTML = "";
    sessions.forEach(s => {
        const item = document.createElement("div");
        item.className = "session-item" + (s.id === currentSessionId ? " active" : "");

        // 标题(可点击切换会话)
        const title = document.createElement("span");
        title.className = "session-title";
        title.textContent = s.title;
        title.onclick = () => switchSession(s.id);

        // 删除按钮(×,hover 显示)
        const del = document.createElement("button");
        del.className = "session-delete";
        del.textContent = "×";
        del.title = "删除该会话";
        del.onclick = (e) => {
            e.stopPropagation();   // 阻止冒泡到会话切换
            deleteSession(s.id);
        };

        item.appendChild(title);
        item.appendChild(del);
        list.appendChild(item);
    });
}

// ---------- 删除单个会话 ----------
function deleteSession(id) {
    const sessions = loadSessions();
    const idx = sessions.findIndex(s => s.id === id);
    if (idx === -1) return;

    sessions.splice(idx, 1);            // 从 localStorage 删除
    saveSessions(sessions);

    if (currentSessionId === id) {      // 删的是当前会话 → 新建一个
        newChat();
    } else {
        renderSessionList();
    }
}

// ---------- 消息渲染 ----------
function addMessage(role, content) {
    const messages = document.getElementById("messages");
    const div = document.createElement("div");
    div.className = "message " + role;

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    if (content) bubble.textContent = content;
    div.appendChild(bubble);
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    return bubble;   // 返回气泡,流式时往里追加文本
}

// ---------- 新建 / 切换会话 ----------
function newChat() {
    currentSessionId = "s-" + Date.now();
    document.getElementById("messages").innerHTML = "";
    renderSessionList();
    document.getElementById("input").focus();
}

function switchSession(id) {
    currentSessionId = id;
    document.getElementById("messages").innerHTML = "";
    const sessions = loadSessions();
    const session = sessions.find(s => s.id === id);
    if (session) {
        session.messages.forEach(m => addMessage(m.role, m.content));
    }
    renderSessionList();
}

// ---------- 核心:读取 SSE 流 ----------
// 浏览器 EventSource 只支持 GET,我们的接口是 POST,所以用 fetch 手动读流
// onEvent(data): 处理每个事件;返回 true 表示结束,停止读取
async function readSSE(response, onEvent) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

        // SSE 事件之间用空行分隔,按空行切成一块块
        let idx;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
            const block = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 2);

            // 取 data: 那一行
            const dataLine = block.split("\n").find(l => l.startsWith("data:"));
            if (!dataLine) continue;

            const data = JSON.parse(dataLine.slice(5).trim());
            if (onEvent(data)) return;   // 回调返回 true = 结束
        }
    }
}

// ---------- 发送消息 ----------
async function sendMessage() {
    if (sending) return;
    const input = document.getElementById("input");
    const text = input.value.trim();
    const imageUrl = currentImageDataUrl;   // 多模态:如果有图就带上
    if (!text && !imageUrl) return;

    input.value = "";
    input.style.height = "auto";
    clearImage();   // 用完即清
    sending = true;
    document.getElementById("sendBtn").disabled = true;

    // 1. 显示用户消息
    addMessage("user", text || "[图片]");

    // 2. 创建 AI 气泡(先显示"思考中...")
    const aiBubble = addMessage("assistant", "");
    const thinking = document.createElement("span");
    thinking.className = "thinking";
    thinking.textContent = "思考中...";
    aiBubble.appendChild(thinking);

    // 3. 发请求,读流
    try {
        const response = await fetch("/api/chat_stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ Id: currentSessionId, Question: text, image_url: imageUrl }),
        });

        let fullAnswer = "";
        await readSSE(response, (data) => {
            if (data.type === "done") return true;
            if (data.type !== "content") return false;
            // 第一个字来了,移除"思考中..."
            if (thinking.parentNode) thinking.remove();
            aiBubble.textContent += data.data;
            fullAnswer += data.data;
            document.getElementById("messages").scrollTop =
                document.getElementById("messages").scrollHeight;
            return false;
        });

        // 4. 保存会话到 localStorage
        const sessions = loadSessions();
        const existing = sessions.find(s => s.id === currentSessionId);
        if (existing) {
            existing.messages.push({ role: "user", content: text });
            existing.messages.push({ role: "assistant", content: fullAnswer });
        } else {
            sessions.unshift({
                id: currentSessionId,
                title: text.slice(0, 20),
                messages: [
                    { role: "user", content: text },
                    { role: "assistant", content: fullAnswer },
                ],
            });
        }
        saveSessions(sessions);
        renderSessionList();

    } catch (err) {
        aiBubble.textContent = "出错了: " + err.message;
    } finally {
        sending = false;
        document.getElementById("sendBtn").disabled = false;
    }
}

// ---------- 主题切换(白天/黑夜) ----------
const themeBtn = document.getElementById("themeBtn");

function applyTheme() {
    const isLight = localStorage.getItem("theme") === "light";
    document.body.classList.toggle("light-theme", isLight);
    themeBtn.textContent = isLight ? "🌙" : "☀️";
}

themeBtn.onclick = () => {
    const isLight = document.body.classList.contains("light-theme");
    localStorage.setItem("theme", isLight ? "dark" : "light");
    applyTheme();
};

// ---------- AIOps 诊断 ----------
document.getElementById("aiopsBtn").onclick = startDiagnosis;

async function startDiagnosis() {
    if (sending) return;
    sending = true;
    document.getElementById("aiopsBtn").disabled = true;

    newChat();   // 干净的会话展示诊断过程

    // 诊断面板
    const panel = addMessage("assistant", "");
    panel.innerHTML = "";

    const title = document.createElement("div");
    title.className = "diag-title";
    title.textContent = "🔧 AIOps 智能诊断";
    panel.appendChild(title);

    const statusLine = document.createElement("div");
    statusLine.className = "diag-status";
    statusLine.textContent = "正在制定诊断计划...";
    panel.appendChild(statusLine);

    try {
        // 1. 提交诊断任务:立即返回 task_id(202,后台异步执行)
        const submitResp = await fetch("/api/aiops", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: currentSessionId }),
        });
        const submitData = await submitResp.json();
        if (submitData.code !== 202) {
            throw new Error(submitData.detail || "诊断任务提交失败");
        }
        const taskId = submitData.task_id;

        // 2. 订阅 SSE 事件流(先回放历史,再实时)
        const response = await fetch(`/api/aiops/${taskId}/events`);

        await readSSE(response, (data) => {
            if (data.type === "plan") {
                // 计划:渲染步骤列表
                statusLine.textContent = `计划已制定,共 ${data.plan.length} 个步骤`;
                const list = document.createElement("div");
                list.className = "diag-plan";
                data.plan.forEach((step, i) => {
                    const item = document.createElement("div");
                    item.className = "diag-plan-item";
                    item.textContent = (i + 1) + ". " + step;
                    list.appendChild(item);
                });
                panel.appendChild(list);
            } else if (data.type === "step_complete") {
                // 步骤完成:追加一行
                const item = document.createElement("div");
                item.className = "diag-step";
                item.textContent = "✅ " + data.current_step;
                panel.appendChild(item);
                statusLine.textContent = data.message;
            } else if (data.type === "report") {
                // 最终报告:单独气泡展示
                statusLine.textContent = "诊断完成";
                addMessage("assistant", data.report);
            } else if (data.type === "complete") {
                return true;   // 结束
            } else if (data.type === "error") {
                statusLine.textContent = "❌ " + data.message;
                return true;
            }
            return false;
        });

        document.getElementById("messages").scrollTop =
            document.getElementById("messages").scrollHeight;
    } catch (err) {
        statusLine.textContent = "出错了: " + err.message;
    } finally {
        sending = false;
        document.getElementById("aiopsBtn").disabled = false;
    }
}

// ---------- 文档上传 ----------
document.getElementById("uploadBtn").onclick = () => document.getElementById("fileInput").click();

document.getElementById("fileInput").onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const status = document.getElementById("uploadStatus");
    status.textContent = "上传中: " + file.name + " ...";

    try {
        const formData = new FormData();
        formData.append("file", file);

        const resp = await fetch("/api/upload", { method: "POST", body: formData });
        const data = await resp.json();

        if (data.code === 200) {
            status.textContent = "✅ " + file.name + " 已入库(" + data.data.chunks + " 分片)";
        } else {
            status.textContent = "❌ " + (data.detail || "上传失败");
        }
    } catch (err) {
        status.textContent = "❌ " + err.message;
    }
    e.target.value = "";   // 清空选择,允许重复上传同一文件
};

// ---------- 多模态:图片输入 ----------
document.getElementById("attachBtn").onclick = () => document.getElementById("imageInput").click();
document.getElementById("imageInput").onchange = (e) => {
    const file = e.target.files[0];
    if (file) setImageFromFile(file);
    e.target.value = "";
};
document.getElementById("removeImageBtn").onclick = clearImage;

// 支持粘贴图片(Ctrl+V)
document.getElementById("input").addEventListener("paste", (e) => {
    const items = (e.clipboardData || e.originalEvent.clipboardData).items || [];
    for (const item of items) {
        if (item.type.indexOf("image") === 0) {
            const file = item.getAsFile();
            if (file) {
                setImageFromFile(file);
                e.preventDefault();
            }
        }
    }
});

function setImageFromFile(file) {
    const reader = new FileReader();
    reader.onload = (e) => setImage(e.target.result);
    reader.readAsDataURL(file);
}

function setImage(dataUrl) {
    currentImageDataUrl = dataUrl;
    document.getElementById("previewImg").src = dataUrl;
    document.getElementById("imagePreview").hidden = false;
}

function clearImage() {
    currentImageDataUrl = null;
    document.getElementById("imagePreview").hidden = true;
    document.getElementById("previewImg").src = "";
}

// ---------- 清除长期记忆 ----------
document.getElementById("memoryClearBtn").onclick = async () => {
    if (!confirm("确定清除全部长期记忆?此操作不可恢复!")) return;
    const status = document.getElementById("uploadStatus");
    status.textContent = "清除中...";
    try {
        const resp = await fetch("/api/memory/clear", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        });
        const data = await resp.json();
        if (data.code === 200) {
            status.textContent = "✅ " + data.message;
            // 同步清空前端 localStorage 的会话记录(保持两边一致)
            localStorage.removeItem("sessions");
            newChat();
        } else {
            status.textContent = "❌ " + (data.detail || "失败");
        }
    } catch (err) {
        status.textContent = "❌ " + err.message;
    }
};

// ---------- 事件绑定 ----------
document.getElementById("sendBtn").onclick = sendMessage;
document.getElementById("input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// 输入框高度自适应
document.getElementById("input").addEventListener("input", (e) => {
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 150) + "px";
});

// ---------- 启动 ----------
applyTheme();   // 恢复上次选择的主题
newChat();
