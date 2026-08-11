// ============================================================
// 迷你 Markdown 渲染器 —— 零依赖,输出安全 HTML
// 支持:标题 / 粗体 / 斜体 / 行内代码 / 代码块 / 列表 / 表格 / 引用 / 分隔线
// 安全:所有内容先 HTML 转义,不解析任何原始 HTML 标签(防 XSS)
// ============================================================

function escapeHtml(s) {
    return s
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

// 行内语法:行内代码 → 粗体 → 斜体(顺序敏感)
function inlineMarkdown(s) {
    return s
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

// 表格行拆分:兼容首尾有无 | 两种写法
function splitRow(row) {
    let r = row.trim();
    if (r.startsWith("|")) r = r.slice(1);
    if (r.endsWith("|")) r = r.slice(0, -1);
    return r.split("|").map(c => c.trim());
}

function renderMarkdown(text) {
    if (!text) return "";
    const lines = escapeHtml(String(text)).replace(/\r\n/g, "\n").split("\n");
    const out = [];
    let i = 0;

    while (i < lines.length) {
        const line = lines[i];

        // 代码块(``` 或 ~~~ 围栏)
        if (/^\s*(```|~~~)/.test(line)) {
            const buf = [];
            i++;
            while (i < lines.length && !/^\s*(```|~~~)/.test(lines[i])) {
                buf.push(lines[i]);
                i++;
            }
            i++; // 跳过结束围栏
            out.push("<pre><code>" + buf.join("\n") + "</code></pre>");
            continue;
        }

        // 表格:当前行含 | 且下一行是分隔行(|---| 或 | :---: |)
        if (line.includes("|") && i + 1 < lines.length &&
            /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/.test(lines[i + 1]) &&
            lines[i + 1].includes("-")) {
            const header = splitRow(line).map(c => "<th>" + inlineMarkdown(c) + "</th>").join("");
            const body = [];
            i += 2;
            while (i < lines.length && lines[i].includes("|")) {
                body.push("<tr>" + splitRow(lines[i]).map(c => "<td>" + inlineMarkdown(c) + "</td>").join("") + "</tr>");
                i++;
            }
            out.push("<table><thead><tr>" + header + "</tr></thead><tbody>" + body.join("") + "</tbody></table>");
            continue;
        }

        // 标题(# ## ###)
        const h = line.match(/^(#{1,3})\s+(.*)$/);
        if (h) {
            const level = h[1].length;
            out.push("<h" + level + ">" + inlineMarkdown(h[2]) + "</h" + level + ">");
            i++;
            continue;
        }

        // 无序列表
        if (/^\s*[-*+]\s+/.test(line)) {
            const items = [];
            while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
                items.push("<li>" + inlineMarkdown(lines[i].replace(/^\s*[-*+]\s+/, "")) + "</li>");
                i++;
            }
            out.push("<ul>" + items.join("") + "</ul>");
            continue;
        }

        // 有序列表
        if (/^\s*\d+\.\s+/.test(line)) {
            const items = [];
            while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
                items.push("<li>" + inlineMarkdown(lines[i].replace(/^\s*\d+\.\s+/, "")) + "</li>");
                i++;
            }
            out.push("<ol>" + items.join("") + "</ol>");
            continue;
        }

        // 引用(注意:内容已 HTML 转义,> 变成 &gt;)
        if (/^\s*&gt;\s?/.test(line)) {
            const buf = [];
            while (i < lines.length && /^\s*&gt;\s?/.test(lines[i])) {
                buf.push(inlineMarkdown(lines[i].replace(/^\s*&gt;\s?/, "")));
                i++;
            }
            out.push("<blockquote>" + buf.join("<br>") + "</blockquote>");
            continue;
        }

        // 分隔线
        if (/^\s*([-*_])\s*(\1\s*){2,}$/.test(line)) {
            out.push("<hr>");
            i++;
            continue;
        }

        // 空行:跳过
        if (line.trim() === "") {
            i++;
            continue;
        }

        // 普通段落:收集到下一个块级语法或空行为止
        const buf = [];
        while (i < lines.length && lines[i].trim() !== "" &&
               !/^\s*(```|~~~|#{1,3}\s+|[-*+]\s+|\d+\.\s+|&gt;\s?|([-*_])\s*(\1\s*){2,}$)/.test(lines[i]) &&
               !(lines[i].includes("|") && i + 1 < lines.length &&
                 /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes("-"))) {
            buf.push(inlineMarkdown(lines[i]));
            i++;
        }
        if (buf.length) out.push("<p>" + buf.join("<br>") + "</p>");
    }

    return out.join("\n");
}
