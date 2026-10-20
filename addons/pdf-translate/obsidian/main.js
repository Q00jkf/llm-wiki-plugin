/* PDF 翻譯（pdf-translate）—— 2026-10-18
 * 右側欄跟著 PDF 目前頁顯示繁中譯文：翻頁 → 停 1 秒 → 抓該頁文字送 Claude API（串流，邊翻邊出現）→ 存快取 → 預翻下一頁。
 * 文字太少（掃描頁）改送頁面影像。key 讀 Windows 環境變數，不存在任何檔案裡；外掛與譯文進 git 共享（使用者 10-18），
 * 沒有 key 的同事只看得到已翻好的頁。要改走自己的轉發伺服器（金鑰不發給個人）→ vault 放 local-config.json，見 CONN。
 * 快取 cache/<PDF 內容 sha1 前 16 碼>/<頁>.md：搬檔改名照樣命中；一頁一檔，兩人同翻一份不會 git 衝突。
 * 頁碼與 pdf.js 物件走 Obsidian 未公開結構（view.viewer.child.pdfViewer.pdfViewer），Obsidian 改版可能失效。
 */
const { Plugin, ItemView, MarkdownRenderer, Modal, Setting, Notice } = require("obsidian");
const { execFileSync, execFile } = require("child_process");
const fs = require("fs"), nodePath = require("path"), crypto = require("crypto");

const VIEW = "pdf-translate";
/* 連線：預設直連 Anthropic、金鑰讀 ANTHROPIC_API_KEY。vault 可用 local-config.json 改走自己的轉發伺服器：
 * { "endpoint": "http://<伺服器>/v1/messages", "keyEnv": "<環境變數名>" } —— 檔裡只寫「去哪個環境變數拿」，
 * 通行碼本身放各人電腦的環境變數，不進 git。安裝／更新模組不覆蓋此檔。 */
const CONN = { endpoint: "https://api.anthropic.com/v1/messages", keyEnv: "ANTHROPIC_API_KEY", custom: false };
function loadConn(dir) {
  let c;
  try { c = JSON.parse(fs.readFileSync(nodePath.join(dir, "local-config.json"), "utf8")); } catch { return; }
  if (typeof c.endpoint === "string" && /^https?:\/\/[^\s]+$/.test(c.endpoint)) { CONN.endpoint = c.endpoint; CONN.custom = true; }
  if (typeof c.keyEnv === "string" && /^[A-Za-z_][A-Za-z0-9_]*$/.test(c.keyEnv)) CONN.keyEnv = c.keyEnv;
}
const MODEL = "claude-sonnet-5-5"; // 便宜一點改 claude-haiku-5-5
/* 金額換算（使用者 10-18）：US$／百萬 tokens [輸入, 輸出]，claude.com/pricing 2026-10-18 查；Haiku 取 ≤100K 級距。匯率為粗估，換算只供參考，實際以 Console 帳單為準 */
const PRICES = { "claude-sonnet-5-5": [2, 10], "claude-opus-5-5": [4, 20], "claude-haiku-5-5": [0.1, 0.5] };
const USD_TWD = 32; // 2026-10-18 查到的最近資料為 7 月約 31.5–32.4，未確認當日匯率
const usdOf = (inTok, outTok) => { const p = PRICES[MODEL]; return p ? (inTok * p[0] + outTok * p[1]) / 1e6 : 0; };
function money(inTok, outTok) {
  if (!PRICES[MODEL]) return "";
  const usd = usdOf(inTok, outTok);
  return `・約 NT$${(usd * USD_TWD).toFixed(2)}（US$${usd.toFixed(4)}）`;
}

/* 問 wiki 每題用量上限（使用者 10-19「限制 tokens 使用量」；每日上限不要）：累計超過就停止查詢、依現有資料作答 */
const ASK_TOKEN_CAP = 60000; // 約 NT$2–4
const MIN_TEXT = 40;  // 去空白後少於這麼多字 → 當掃描頁送圖
const DEBOUNCE = 1000; // 快速連翻不要每頁都送（使用者 10-18 定 1 秒）
const LS_AUTO = "pdf-translate-auto"; // 自動翻譯開關，預設關（使用者 10-18「不是每一個都需要翻譯」）；關閉時快取照樣顯示
const SYSTEM = `你是電子／導航產品的技術文件翻譯。把使用者給的 PDF 單頁內容翻成繁體中文（台灣用語）。
- 保留原文段落與標題結構，輸出 Markdown；表格輸出成 Markdown 表格。
- 數值、單位、型號、料號、腳位名、暫存器名、指令、程式碼維持原文不翻。
- 專有名詞第一次出現時在括號附原文，例如「零偏（bias）」。
- 頁首頁尾、頁碼、版權聲明可省略。
- 照原文分段，不要合併相鄰段落。
- 對位標記：每個標題、段落、清單、表格的前一行單獨放 <!--y:NN-->，NN＝該段頂端在頁面的垂直位置（0＝頁頂、100＝頁底）。文字稿每行開頭的 ⟨NN⟩ 就是那一行的位置，取該段第一行的數字；看圖時自行估計。⟨NN⟩ 本身不要輸出。
- 只輸出譯文，不要加任何說明。`;
/* 對位標記（主管 10-19「左邊只有三排字，右邊也只顯示那幾排的翻譯」）：譯文切成段，每段記原頁垂直位置；舊快取沒有標記就退回比例跟隨 */
const MARK = /<!--y:(\d{1,3})-->/;
const stripMarks = (md) => md.replace(/<!--[yb]:\d{1,4}-->\s*/g, "");
const LAYOUT_SYSTEM = `你是電子／導航產品的技術文件翻譯。使用者給的是 PDF 單頁按版面切好的文字區塊，每行一塊，開頭 ⟦N⟧ 是區塊編號（可能是標題、段落、表格儲存格、圖說）。
- 每塊翻成繁體中文（台灣用語）。輸出格式固定：<!--b:N-->譯文，一塊一行，塊與塊之間空一行；編號照給的，不要合併、拆開或漏掉。
- 只輸出純文字，不要加 Markdown 符號（#、**、表格線）。
- 數值、單位、型號、料號、腳位名、暫存器名、指令、程式碼維持原文；不用翻的塊（純型號、專有名稱）照原文輸出。
- 專有名詞第一次出現時在括號附原文，例如「零偏（bias）」。
- 譯文要放回原本的位置，長度盡量精簡、接近原文。
- 只輸出譯文，不要加任何說明。`;
function segments(md) {
  const parts = md.split(MARK); // [前言, y, 段, y, 段, …]
  if (parts.length < 3) return null;
  const segs = parts[0].trim() ? [{ y: 0, md: parts[0] }] : [];
  for (let i = 1; i < parts.length; i += 2) segs.push({ y: Math.min(100, +parts[i]), md: parts[i + 1] });
  for (const s of segs) s.y1 = Math.min(100, ...segs.map((t) => t.y).filter((y) => y > s.y)); // 雙欄時順序不一定遞增
  return segs;
}

/* 選取文字的 AI 動作（使用者 10-18）：右鍵選單＋命令（可綁快捷鍵）；結果顯示在同一側欄 */
const ASSIST = {
  translate: { title: "翻譯", system: `把使用者給的文字翻成繁體中文（台灣用語）；原文已是中文就翻成英文。數值、單位、型號、指令、程式碼維持原文。只輸出譯文。` },
  explain: { title: "解釋", ask: true }, // 走「問 wiki」（使用者 10-19 同意解釋改用它）
  formal: { title: "改寫成正式中文", replace: true, system: `把使用者給的文字改寫成正式、通順的繁體中文書面語（台灣用語），意思不增不減，保留數值與專有名詞。只輸出改寫結果。` },
  formalEn: { title: "改寫成正式英文", replace: true, system: `把使用者給的文字（中文或英文皆可）改寫成正式、精確的英文技術書面語，意思不增不減，保留數值、單位與專有名詞；不要寫成信件格式。只輸出改寫結果。
若內容出現晶片、感測器、模組的型號或廠牌，在結果後另起一行「---」，用繁體中文列出並提醒「對外文件請先確認可否揭露內部使用的型號」；沒有就不要加這段。` },
};

/* key：先看 process.env；Obsidian 比環境變數早開時讀不到，改直接讀使用者層級登錄 */
function apiKey() {
  const name = CONN.keyEnv; // loadConn 已限制成合法變數名，可安全放進 RegExp
  if (process.env[name]) return process.env[name];
  try {
    const out = execFileSync("reg", ["query", "HKCU\\Environment", "/v", name], { encoding: "utf8", windowsHide: true });
    const m = out.match(new RegExp(name + "\\s+REG_\\w+\\s+(\\S+)"));
    return m ? m[1] : "";
  } catch { return ""; }
}

function headers() {
  const key = apiKey();
  if (!key) throw new Error(CONN.custom
    ? `這台電腦沒有設定 ${CONN.keyEnv}（轉發伺服器的個人通行碼），只能看已經翻好的頁；請向管理者申請`
    : `這台電腦沒有設定 ${CONN.keyEnv}，只能看已經翻好的頁`);
  return { "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01", "anthropic-dangerous-direct-browser-access": "true" };
}

/* 版面對照（使用者 10-19「變得跟 PDF 相同的格式」）：文字層切成區塊（段落／儲存格／標題），座標以 scale 1 viewport 為準；翻譯與畫面都用同一份切法 */
const TR_RE = /[A-Za-z]{2,}/;
const BULLET_RE = /^[•·▪◦‣●○■□➢►–]/; // 沒有英文字的塊（純數字、料號片段）不送翻，直接看原圖
async function pageBlocks(page) {
  const vp = page.getViewport({ scale: 1 }), tc = await page.getTextContent();
  const runs = [];
  let r = null, eol = true;
  for (const i of tc.items) {
    if (!i.str) { if (i.hasEOL) eol = true; continue; }
    const t = i.transform, fs = Math.hypot(t[2], t[3]) || 10, [x, yb] = vp.convertToViewportPoint(t[4], t[5]);
    const same = r && !eol && Math.abs(yb - r.yb) < fs * 0.5 && x >= r.x + r.w - fs && x - (r.x + r.w) < fs * 1.5; // 同一行且間距小＝同一塊；大間距＝表格下一格
    if (same) { r.text += i.str; r.w = Math.max(r.w, x + i.width - r.x); }
    else if (i.str.trim()) runs.push(r = { x, yb, y: yb - fs, w: i.width, h: fs * 1.2, fs, text: i.str });
    eol = i.hasEOL;
  }
  const blocks = [];
  for (const r of runs) { // 左緣對齊、字級相同、行距小 → 併成同一段
    r.text = r.text.trim();
    // 不併：條列符號開頭、字級不同（標題）、上一行很短（表格儲存格或段尾）
    const b = !BULLET_RE.test(r.text) && blocks.slice(-6).reverse().find((b) => Math.abs(b.x - r.x) < b.fs * 1.2 && Math.abs(b.fs - r.fs) < Math.max(0.5, b.fs * 0.06)
      && r.y >= b.y && r.y - (b.y + b.h) < b.fs * 0.8 && b.lastW >= Math.max(12 * b.fs, 0.7 * Math.max(b.w, r.w)));
    if (!b) { blocks.push({ x: r.x, y: r.y, w: r.w, h: r.h, fs: r.fs, text: r.text, lastW: r.w }); continue; }
    b.lastW = r.w;
    b.text += (/-$/.test(b.text) ? "" : " ") + r.text;
    const right = Math.max(b.x + b.w, r.x + r.w);
    b.x = Math.min(b.x, r.x); b.w = right - b.x; b.h = r.y + r.h - b.y;
  }
  return { W: vp.width, H: vp.height, blocks: blocks.map((b, i) => ({ ...b, id: i + 1 })) };
}

/* 框四角取色，取中位數（文字壓到某個角也不影響） */
function bgAt(g, x, y, w, h) {
  const px = [[x, y], [x + w, y], [x, y + h], [x + w, y + h]].map(([a, b]) => {
    try { return [...g.getImageData(Math.max(0, Math.round(a)), Math.max(0, Math.round(b)), 1, 1).data.slice(0, 3)]; } catch { return null; }
  }).filter(Boolean);
  if (!px.length) return null;
  px.sort((p, q) => p[0] + p[1] + p[2] - (q[0] + q[1] + q[2]));
  return px[Math.floor(px.length / 2)];
}

/* 一頁 → API content：有文字層走版面對照（逐塊翻），沒有就畫成 JPEG 送圖 */
async function pageContent(doc, n) {
  const page = await doc.getPage(n);
  const { blocks } = await pageBlocks(page);
  const todo = blocks.filter((b) => TR_RE.test(b.text));
  if (blocks.map((b) => b.text).join("").replace(/\s/g, "").length >= MIN_TEXT && todo.length)
    return { layout: true, content: [{ type: "text", text: todo.map((b) => `⟦${b.id}⟧ ${b.text}`).join("\n") }] };
  const vp = page.getViewport({ scale: 1.6 });
  const c = document.createElement("canvas");
  c.width = vp.width; c.height = vp.height;
  await page.render({ canvasContext: c.getContext("2d"), viewport: vp }).promise;
  const data = c.toDataURL("image/jpeg", 0.85).split(",")[1];
  return { layout: false, content: [{ type: "image", source: { type: "base64", media_type: "image/jpeg", data } }, { type: "text", text: "請翻譯這一頁。" }] };
}

/* 圖片檔（使用者 10-19「jpg PNG 也加進去」）：長邊縮到 1568 px（API 建議上限，再大只是多花 token）轉 JPEG 送出 */
const IMG_EXT = ["png", "jpg", "jpeg", "gif", "webp"];
async function imageContent(app, file) {
  const url = app.vault.getResourcePath(file);
  const img = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => rej(new Error("圖片讀不到")); i.src = url; });
  const k = Math.min(1, 1568 / Math.max(img.naturalWidth, img.naturalHeight));
  const c = document.createElement("canvas");
  c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k);
  const g = c.getContext("2d");
  g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height); // 透明 PNG 墊白底
  g.drawImage(img, 0, 0, c.width, c.height);
  const data = c.toDataURL("image/jpeg", 0.9).split(",")[1];
  return [{ type: "image", source: { type: "base64", media_type: "image/jpeg", data } }, { type: "text", text: "請翻譯這張圖片裡的文字；圖片裡沒有文字就簡短說明圖片內容。" }];
}

/* 串流呼叫（含 tool use）；onText 每收到一段就回傳本輪累積的文字 */
async function chat(body, onText) {
  const res = await fetch(CONN.endpoint, {
    method: "POST", headers: headers(),
    body: JSON.stringify({ model: MODEL, max_tokens: 8000, stream: true, ...body }),
  });
  if (!res.ok) throw new Error(`API ${res.status}：${(await res.text()).slice(0, 300)}`);
  const reader = res.body.getReader(), dec = new TextDecoder();
  const blocks = [], usage = { in: 0, out: 0 };
  let buf = "", text = "", stop = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (!line.startsWith("data:")) continue;
      const ev = JSON.parse(line.slice(5));
      if (ev.type === "content_block_start") {
        const b = ev.content_block;
        blocks[ev.index] = b.type === "tool_use" ? { type: "tool_use", id: b.id, name: b.name, json: "" } : { type: "text", text: "" };
      } else if (ev.type === "content_block_delta") {
        const b = blocks[ev.index];
        if (ev.delta.type === "text_delta") { b.text += ev.delta.text; text += ev.delta.text; onText(text); }
        else if (ev.delta.type === "input_json_delta") b.json += ev.delta.partial_json;
      } else if (ev.type === "content_block_stop") {
        const b = blocks[ev.index];
        if (b && b.type === "tool_use") { b.input = b.json ? JSON.parse(b.json) : {}; delete b.json; }
      } else if (ev.type === "message_start") usage.in = ev.message.usage.input_tokens;
      else if (ev.type === "message_delta") { usage.out = ev.usage.output_tokens; stop = ev.delta.stop_reason || stop; }
      else if (ev.type === "error") throw new Error(ev.error.message);
    }
  }
  return { blocks: blocks.filter((b) => b && (b.type !== "text" || b.text)), text, usage, stop };
}

const translate = async (content, system, onText) => {
  const r = await chat({ system, messages: [{ role: "user", content }] }, onText);
  return { text: r.text, usage: r.usage };
};

/* ── 問 wiki（使用者 10-19：只搜 wiki/；進度題請問負責人）：查法照 plugin llm-wiki:wiki-query ── */
const MAX_ROUNDS = 8;
const SKIP_SEARCH = ["wiki/log.md", "wiki/synthesis/status.md"]; // log 走 log_query（熱門產品 grep 一次回幾百行）；status.md 已停止維護
const ASK_SYSTEM = (products) => `你是團隊 wiki 的查詢助理，替同事回答問題。只能用工具查 wiki/ 資料夾；raw/ 正本、腳本、網路都不能用。用繁體中文回答。

## 查詢順序（由便宜到貴，夠了就停）
1. wiki/hot.md（最近上下文）
2. search_wiki 定位到哪幾頁、哪幾行；不要整頁讀
3. wiki/index.md（需要全局視野才讀）
4. read_page 只讀命中處的行段（帶 offset／limit）
歷程、裁示、「以前怎麼決定的」→ log_query 找條目，再 read_page wiki/log.md 讀那幾行；不要用 search_wiki 搜 log。

## 防混淆（產品間術語高度重疊，例如 PPS、雙天線）
產品清單：${products}。
1. 問題指到某產品 → search_wiki 的 path 限定到 wiki/products/<產品>.md、wiki/concepts/<產品>/ 等；命中頁看 product／scope，不是目標產品就不採用。wiki/concepts/shared/ 是通用頁，可用但要標明「通用」。
2. 問題沒指產品、而答案會因產品不同 → 先回問「請問是哪個產品？」，不要全域猜。
3. 只講目標產品；使用者明問差異才並列。

## 指標卡
tier 為 1 或 type 為 doc-index 的頁故意不放數值：不要引用它上面的數字當答案，改告訴同事數值在哪份正本的第幾節／第幾頁，附上頁上給的正本連結。

## 不在 wiki 的題型（說明怎麼查，不要猜）
- 進度／狀態（「XX 到哪了」「卡在哪」「現在怎樣」）：回答「wiki 沒有維護進度紀錄，請直接問負責人」，不拿舊紀錄拼湊。

## 回答格式
- 開頭直接給結論；能用表格就用表格。
- 每個結論後面接出處：[[wiki 頁路徑]] 或「wiki/log.md L行號」。
- 用到 wiki 以外的一般知識，必須標「[⚠️ 非資料庫：一般知識]」。
- 查不到就明說「wiki 中無足夠資料回答此問題」，並列出查了哪幾處、哪些資料可能相關。
- 不確定就說不確定，不要編造數字。`;

/* 問題講到「這頁／這一面／這篇」就附上正在看的 PDF 頁、圖片或筆記 */
const PAGE_RE = /這一?[頁面張篇]|本頁|此頁|這份/;
const NOTE_MAX = 12000; // 字元；筆記超過就只附畫面附近這麼多字
const PAGE_RULES = `

## 本頁模式
- 使用者附了正在看的頁面；問題裡的「這頁／這一面／這份」指的就是它。
- 先依頁面內容回答：重點摘要、圖表與表格在說什麼、關鍵術語。頁面上的內容直接引用，出處寫「本頁」，不必查 wiki。
- 需要連到我們產品或裁示時再用工具查 wiki，有查才附 wiki 出處。
- 頁面沒寫、wiki 也查無的內容用一般知識補，要標「[⚠️ 非資料庫：一般知識]」。`;

const TOOLS = [
  { name: "search_wiki", description: "在 wiki/ 全文搜尋（不分大小寫；多個關鍵字用空白分開，命中越多排越前）。回傳每頁的 product／scope／tier 與命中行號＋片段。不搜 wiki/log.md。",
    input_schema: { type: "object", properties: { query: { type: "string" }, path: { type: "string", description: "限定範圍，例如 wiki/concepts/<產品> 或 wiki/products/<產品>.md；不填＝整個 wiki/" } }, required: ["query"] } },
  { name: "read_page", description: "讀 wiki/ 內一頁，回傳帶行號的內容。大頁請帶 offset／limit 只讀需要的段落。",
    input_schema: { type: "object", properties: { path: { type: "string" }, offset: { type: "integer", description: "起始行（1 起算）" }, limit: { type: "integer", description: "行數，預設 200，最多 400" } }, required: ["path"] } },
  { name: "list_dir", description: "列出 wiki/ 內某資料夾的子資料夾與頁面（附 product）。",
    input_schema: { type: "object", properties: { path: { type: "string" } }, required: ["path"] } },
  { name: "log_query", description: "查 wiki/log.md 條目（依標記 <!-- log kind:… scope:… -->）。回傳日期、kind、標題與行號，新的在前；再用 read_page wiki/log.md offset=行號 讀內容。",
    input_schema: { type: "object", properties: { scope: { type: "string", description: "產品或主題，例如 <產品>、協作" }, kind: { type: "string", description: "例如 裁示、ingest、工具、收尾" }, keyword: { type: "string", description: "標題關鍵字" } } } },
];

function wikiPath(p) {
  p = String(p || "wiki").replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  if (p !== "wiki" && !p.startsWith("wiki/")) p = "wiki/" + p;
  if (p.split("/").includes("..")) throw new Error("路徑不可含 ..");
  return p;
}

function metaOf(app, f) {
  const fm = (app.metadataCache.getFileCache(f) || {}).frontmatter || {};
  const m = [];
  for (const k of ["product", "products", "scope", "tier", "type"]) if (fm[k] != null) m.push(`${k}: ${[].concat(fm[k]).join(",")}`);
  return m.join("；") || "未標";
}

async function runTool(app, name, input) {
  const files = app.vault.getMarkdownFiles();
  if (name === "search_wiki") {
    const terms = String(input.query || "").toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return "query 不可空白";
    const base = wikiPath(input.path).replace(/\.md$/, "");
    const hits = [];
    for (const f of files) {
      if (!(f.path === base + ".md" || f.path.startsWith(base + "/")) || SKIP_SEARCH.includes(f.path)) continue;
      const lines = (await app.vault.cachedRead(f)).split("\n"), name = f.path.toLowerCase();
      const at = [];
      lines.forEach((l, i) => { const low = l.toLowerCase(); if (terms.some((t) => low.includes(t))) at.push(i); });
      const got = terms.filter((t) => name.includes(t) || at.some((i) => lines[i].toLowerCase().includes(t)));
      if (!got.length) continue;
      hits.push({ f, lines, at, score: got.length * 1000 + (terms.some((t) => name.includes(t)) ? 500 : 0) + at.length });
    }
    if (!hits.length) return `「${input.query}」在 ${base} 查無`;
    hits.sort((a, b) => b.score - a.score);
    return `共 ${hits.length} 頁命中，列前 ${Math.min(15, hits.length)} 頁：\n` + hits.slice(0, 15).map((h) =>
      `- ${h.f.path}（${metaOf(app, h.f)}）命中 ${h.at.length} 行\n` + h.at.slice(0, 3).map((i) => `    L${i + 1}: ${h.lines[i].trim().slice(0, 160)}`).join("\n")).join("\n");
  }
  if (name === "read_page") {
    let p = wikiPath(input.path);
    const f = app.vault.getAbstractFileByPath(p) || app.vault.getAbstractFileByPath(p + ".md");
    if (!f || !f.extension) return `${p} 不存在`;
    const lines = (await app.vault.cachedRead(f)).split("\n");
    const off = Math.max(1, input.offset || 1), lim = Math.min(400, input.limit || 200);
    let out = lines.slice(off - 1, off - 1 + lim).map((l, i) => `${off + i}\t${l}`).join("\n");
    if (out.length > 15000) out = out.slice(0, 15000) + "\n…（超過字數上限截斷，請縮小 limit）";
    return `${f.path}（共 ${lines.length} 行；${metaOf(app, f)}）\n${out}`;
  }
  if (name === "list_dir") {
    const d = app.vault.getAbstractFileByPath(wikiPath(input.path));
    if (!d || !d.children) return `${input.path} 不是資料夾`;
    return d.children.slice(0, 200).map((c) => c.children ? `${c.name}/` : `${c.name}${c.extension === "md" ? "（" + metaOf(app, c) + "）" : ""}`).join("\n");
  }
  if (name === "log_query") {
    const f = app.vault.getAbstractFileByPath("wiki/log.md");
    if (!f) return "wiki/log.md 不存在";
    const lines = (await app.vault.cachedRead(f)).split("\n"), low = (s) => String(s || "").toLowerCase(), out = [];
    for (let i = 0; i < lines.length && out.length < 30; i++) {
      if (!lines[i].startsWith("## ")) continue;
      const m = (lines[i + 1] || "").match(/<!--\s*log\s+kind:(\S+)\s+scope:(\S+)/) || [];
      if (input.kind && !low(m[1]).includes(low(input.kind))) continue;
      if (input.scope && !low(m[2]).includes(low(input.scope))) continue;
      if (input.keyword && !low(lines[i]).includes(low(input.keyword))) continue;
      out.push(`L${i + 1}: ${lines[i].slice(3)}（scope:${m[2] || "?"}）`);
    }
    return out.length ? out.join("\n") : "查無符合的 log 條目";
  }
  return `沒有工具 ${name}`;
}

/* ── 日程輔助（使用者 10-19）：口述 → Claude 轉成 agenda.py 指令 → 預覽 → 使用者確認才執行 ──
 * 寫入一律走 agenda.py（CLAUDE.md：Claude 代改帶 --source agenda）；改期／完成／改工期用整行原文當關鍵字，保證唯一命中 */
const WEEK = "日一二三四五六";
const ymd = (d) => d.toLocaleDateString("sv");
const AGENDA_TOOL = { name: "propose", description: "把使用者的話轉成 agenda.py 操作；資訊不足就只填 question，不給 ops。",
  input_schema: { type: "object", properties: {
    ops: { type: "array", items: { type: "object", properties: {
      cmd: { type: "string", enum: ["add", "move", "done", "dur", "link"] },
      line: { type: "string", description: "add：完整一行" },
      target: { type: "integer", description: "move／done／dur／link（後項）：「現有日程」清單的編號" },
      after: { type: "integer", description: "link：前項在「現有日程」的編號" },
      id: { type: "string", description: "link：前項沒有代號時替它取的代號" },
      date: { type: "string", description: "move：新日期 YYYY-MM-DD" },
      days: { type: "integer", description: "dur：新工期（工作天）" },
      say: { type: "string", description: "一句中文說明這筆做什麼" } }, required: ["cmd", "say"] } },
    question: { type: "string", description: "要先問使用者的事；有它就不給 ops" } } } };

function agendaSystem(products, open) {
  const now = new Date(), cal = [];
  for (let i = 0; i < 42; i++) { const d = new Date(now); d.setDate(now.getDate() + i); cal.push(`${ymd(d)}(${WEEK[d.getDay()]})`); }
  const md = ymd(now).slice(5);
  return `你把同事口述的日程轉成 agenda.py 操作。不論結果如何都一定要呼叫 propose 回報（要問問題也用 propose 的 question），不要只回文字。今天是 ${ymd(now)}（週${WEEK[now.getDay()]}）。
未來 6 週日曆（換算「下週三」「月底」用，週一為一週開始）：${cal.join(" ")}

## add 的一行格式（wiki/meta/agenda-system.md）
\`YYYY-MM-DD [HH:MM[-HH:MM]] 類型 標題 [專案欄位] [重複規則] [#tag …] → AI 助手 ${md} 口述\`
- 類型用：會議／交件／待辦／提醒／出差／稽核。會議有講時間就寫（沒講結束時間只寫開始）；沒時間＝全天；地點寫在標題後「@地點」。
- tag 只能用：${products.map((p) => "#" + p).join(" ")} #QMS #行政；看不出來就不加，不自創。
- 標題用使用者的說法精簡寫，不加他沒講的內容。
- 重複規則（使用者講「每個月 23 號」「每週三」「每年 3/1」「每兩週」才加）：\`每月D日\`／\`每週一…日\`／\`每年MM-DD\`／\`每N天\`；行首日期寫最近一次發生的日期；重複事件不加專案欄位。
- 專案欄位（使用者有講才加，放標題後）：
  - \`工期N天\`：做 N 個工作天，**行首日期是最後一天**（「從 10-20 開始做 3 天」→ 行首寫第 3 個工作天）。
  - \`截止:MM-DD\`：期限，只提醒不推日期。
  - \`代號:x\`：之後要被別的事接上時才給，用英數或中文短詞，不可和現有代號重複。
  - \`接:a\`：等代號 a 做完才開始（「等熱板確認完再做」→ 接:ap熱板確認）；前項要在「現有日程」裡有代號，沒有代號就改用 link 操作。可寫 \`接:a+2\`（a 完成後隔 2 工作天）。
  - \`屬:x\`：掛在母項代號 x 底下。
  - 不要寫 \`原定:\`、\`完成:\`、\`進度:\`（由 agenda.py 自動維護）。
- 一連串步驟（例如新訂單：備料→組裝→測試→出貨）：每步一筆、各給代號、用 接: 串起來，前項排在前面。日期寫你估的即可：agenda.py 會依工作天（扣國定假日）自動順延有 接: 的項目。
- 🔴 交件／稽核／會議是硬期限，agenda.py **不會**順延它們。所以有前項的出貨／交件，類型用「待辦」，使用者講的最晚日期寫成 \`截止:\`；只有使用者講死某天交件且沒有前項時才用「交件」。

## 其他操作
- move：改期，date 寫新日期。done：標記完成。dur：改工期，days 寫工作天數。
- link：把已存在的兩件事接起來（target＝後項，after＝前項）；前項沒有代號時在 id 給它取一個。

## 不猜
- 沒講日期、講法有兩種理解（例如今天週三講「這週三」）、時間不明確卻像是會議 → 不給 ops，填 question 問清楚。
- 改期／完成／改工期：從下面「現有日程」挑編號填 target；找不到或有兩筆都像 → 填 question。
- 一句話有多件事就給多筆 ops。

## 現有日程（未完成）
${open.map((l, i) => `${i}. ${l}`).join("\n") || "（無）"}`;
}

/* agenda 一行 → 欄位（預覽給使用者逐欄核對，使用者 10-19） */
const FIELD_RE = [ // [預覽欄名, 正則]；有才列出
  ["重複", /(每月\d+日|每週[一二三四五六日]|每年\d{2}-\d{2}|每\d+天)/], ["工期", /工期(\d+)天/], ["截止", /截止:(\S+)/],
  ["代號", /代號:(\S+)/], ["接在後面（前項）", /接:(\S+)/], ["屬於（母項）", /屬:(\S+)/],
  ["原定", /原定:(\S+)/], ["完成", /完成:(\S+)/], ["進度", /進度:(\S+)/],
];
function fields(line) {
  const m = (line || "").match(/^(\d{4}-\d{2}-\d{2})\s+(?:(\d{2}:\d{2}(?:-\d{2}:\d{2})?)\s+)?(\S+)\s+(.*)$/);
  if (!m) return null;
  let rest = m[4], src = "";
  const at = rest.indexOf("→");
  if (at >= 0) { src = rest.slice(at + 1).trim(); rest = rest.slice(0, at); }
  // tag 要在空白後（標題裡「（#157）」的 # 不是 tag，10-19 實踩）
  const TAG = /(^|\s)#[^\s#]+/g, tags = (rest.match(TAG) || []).map((t) => t.trim()).join(" "), extra = {};
  rest = rest.replace(TAG, "$1");
  for (const [k, re] of FIELD_RE) { const x = rest.match(re); if (x) { extra[k] = k === "工期" ? x[1] + " 個工作天（日期是最後一天）" : x[1]; rest = rest.replace(re, ""); } }
  const loc = (rest.match(/@(\S+)/) || [])[1] || "";
  rest = rest.replace(/@\S+/, "");
  return { date: m[1], 日期: `${m[1]}（週${WEEK[new Date(m[1] + "T00:00").getDay()]}）`, 時間: m[2] || "全天", 類型: m[3],
    名稱: rest.replace(/\s+/g, " ").trim(), 地點: loc || "—", 標籤: tags || "—", ...extra, 出處: src || "—" };
}

class AgendaModal extends Modal {
  constructor(app, plugin) { super(app); this.plugin = plugin; }
  onOpen() {
    const c = this.contentEl;
    c.addClass("pdf-translate");
    c.createEl("h3", { text: "📅 日程輔助" });
    const steps = c.createEl("ol", { cls: "pt-status" });
    steps.createEl("li", { text: "寫下要排的事，用說的就好。例：「下週三下午兩點跟客戶開會，討論規格定版」「把樣品確認改到 10-22」「測試程式做完了」" });
    steps.createEl("li", { text: "按「解析」（或 Ctrl+Enter）：會列出日期、時間、類型、名稱、地點、標籤，逐欄確認是否正確；這一步還不會寫入" });
    steps.createEl("li", { text: "確認無誤再按「寫入 agenda」；不對就改第 1 步的文字重新解析" });
    this.input = c.createEl("textarea", { attr: { rows: 6, style: "width:100%" } });
    this.status = c.createDiv("pt-status");
    this.preview = c.createDiv("pt-body");
    const row = new Setting(c);
    row.addButton((b) => { this.parseBtn = b; b.setButtonText("解析").setCta().onClick(() => this.parse()); });
    row.addButton((b) => { this.writeBtn = b; b.setButtonText("寫入 agenda").setDisabled(true).onClick(() => this.write()); });
    row.addButton((b) => b.setButtonText("關閉").onClick(() => this.close()));
    this.input.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !e.isComposing) this.parse(); });
    setTimeout(() => this.input.focus(), 0);
  }
  async parse() {
    const said = this.input.value.trim();
    if (!said) return;
    this.ops = null; this.writeBtn.setDisabled(true); this.preview.empty();
    this.status.setText("解析中…");
    try {
      const f = this.app.vault.getAbstractFileByPath("wiki/agenda.md");
      if (!f) throw new Error("找不到 wiki/agenda.md");
      const body = (await this.app.vault.read(f)).split("<!-- 事件從下一行開始 -->").pop();
      this.open = body.split("\n").map((l) => l.trim()).filter((l) => /^\d{4}-\d{2}-\d{2}\s/.test(l));
      const pdir = this.app.vault.getAbstractFileByPath("wiki/products");
      const products = pdir && pdir.children ? pdir.children.filter((x) => x.extension === "md").map((x) => x.basename) : [];
      const r = await chat({ system: agendaSystem(products, this.open), tools: [AGENDA_TOOL], max_tokens: 8000, // 一次講十幾件時 2000 不夠（6 件已用 1,544） // 這個模型不支援強制 tool_choice（10-19 API 400），改在 system 要求一定呼叫
        messages: [{ role: "user", content: said }] }, () => {});
      const call = r.blocks.find((b) => b.type === "tool_use") || { input: { question: r.text || "沒有解析出要做的事，請換個說法" } };
      const cost = `輸入 ${r.usage.in}／輸出 ${r.usage.out} tokens${money(r.usage.in, r.usage.out)}`;
      if (call.input.question) { this.status.setText(cost); this.preview.setText("❓ " + call.input.question + "（補充後再按「解析」）"); return; }
      const ops = (call.input.ops || []).map((o) => this.toArgs(o));
      if (!ops.length) { this.status.setText(cost); this.preview.setText("沒有解析出要做的事，請換個說法"); return; }
      this.ops = ops;
      for (const o of ops) {
        const d = this.preview.createDiv();
        d.createEl("b", { text: (o.err ? "⚠️ " : "") + o.say });
        if (o.err) { d.createEl("div", { text: o.err }); continue; }
        const t = d.createEl("table");
        for (const [k, val] of Object.entries(o.rows)) { const tr = t.createEl("tr"); tr.createEl("th", { text: k }); tr.createEl("td", { text: val }); }
        d.createEl("div", { cls: "pt-status", text: "寫進 agenda 的原文：" + o.show });
      }
      let ok = ops.every((o) => !o.err);
      if (ok) ok = await this.simulate(ops);
      this.status.setText(cost + (ok ? "・確認無誤按「寫入 agenda」" : "・有問題的項目不會寫入，請修正說法再解析"));
      this.writeBtn.setDisabled(!ok);
    } catch (e) { this.status.setText("❌ " + e.message); }
  }
  /* 一筆 op → agenda.py 參數；舊行一律用整行原文當關鍵字 */
  toArgs(o) {
    const old = Number.isInteger(o.target) ? this.open[o.target] : null, say = o.say || o.cmd;
    if (o.cmd === "add") {
      const f = fields(o.line);
      if (!f) return { say, err: "格式不對，無法解析：" + (o.line || "（空白）") };
      const { date, ...rows } = f;
      return { say, args: ["add", o.line], show: o.line, rows: { 動作: "新增", ...rows } };
    }
    if (!old) return { say, err: "對不到現有日程" };
    const f = fields(old) || { 名稱: old, 日期: "?" }, base = { 名稱: f.名稱, 類型: f.類型 || "—", 標籤: f.標籤 || "—" };
    if (o.cmd === "done") return { say, args: ["done", old], show: old, rows: { 動作: "標記完成", ...base, 日期: f.日期 } };
    if (o.cmd === "move") {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(o.date || "")) return { say, err: "新日期格式不對" };
      return { say, args: ["move", old, o.date], show: old, rows: { 動作: "改期", ...base, 原日期: f.日期, 新日期: `${o.date}（週${WEEK[new Date(o.date + "T00:00").getDay()]}）`, 注意: "接在它後面的項目會一起順延，寫入後會列出" } };
    }
    if (o.cmd === "link") {
      const pre = Number.isInteger(o.after) ? this.open[o.after] : null;
      if (!pre) return { say, err: "對不到前項" };
      const pf = fields(pre) || { 名稱: pre }, code = (pre.match(/代號:(\S+)/) || [])[1];
      if (!code && !o.id) return { say, err: "前項沒有代號，也沒給新代號" };
      const pcode = code || o.id;
      // agenda.py link 吃「後項關鍵字 前項關鍵字」，不是代號
      return { say, args: ["link", old, pre, ...(code ? [] : ["--id", o.id])], show: `${old}\n接在：${pre}`,
        rows: { 動作: "接在後面（前項做完才開始）", 後項: f.名稱, 前項: pf.名稱, 前項代號: pcode + (code ? "" : "（新取）"), 注意: "後項日期可能被順延，寫入後會列出" } };
    }
    if (o.cmd === "dur") return o.days > 0 ? { say, args: ["dur", old, String(o.days)], show: old, rows: { 動作: "改工期", ...base, 新工期: `${o.days} 個工作天` } } : { say, err: "工期要是正整數" };
    return { say, err: "不支援的操作 " + o.cmd };
  }
  /* 跑 agenda.py（不花 token）；file＝暫存複本時就是模擬 */
  py(args, file) {
    const a = ["scripts/agenda.py", ...args, ...(args[0] === "--check" ? [] : ["--source", "agenda"]), ...(file ? ["--file", file] : [])];
    return new Promise((res) => execFile("python", a, { cwd: this.app.vault.adapter.basePath, windowsHide: true, encoding: "utf8", env: { ...process.env, PYTHONIOENCODING: "utf-8" } },
      (err, so, se) => res({ ok: !err, text: ((so || "") + (se || "") + (err && !se ? err.message : "")).trim() })));
  }

  /* 模擬寫入（10-19 實踩：AI 的日曆不知國定假日，agenda.py 會再順延；交件類硬期限不順延只報晚）：
   * 暫存複本上依序跑一遍，列出順延／平移與 --check 警告，讓使用者看到寫入後的真實日期 */
  async simulate(ops) {
    const os = require("os"), dir = nodePath.join(os.tmpdir(), "pt-agenda-sim"), f = nodePath.join(dir, "agenda.md");
    fs.mkdirSync(dir, { recursive: true });
    fs.copyFileSync(nodePath.join(this.app.vault.adapter.basePath, "wiki", "agenda.md"), f);
    const lines = [];
    let ok = true;
    for (const o of ops) {
      const r = await this.py(o.args, f);
      if (!r.ok) { ok = false; lines.push(`❌ ${o.say}：${r.text}`); break; }
      lines.push(...r.text.split("\n").filter((l) => /^(順延|平移)/.test(l)));
    }
    if (ok) {
      const chk = await this.py(["--check"], f), base = await this.py(["--check"]);
      const old = new Set(base.text.split("\n").map((l) => l.replace(/L\d+/, "")));
      lines.push(...chk.text.split("\n").filter((l) => /🔴|⚠️/.test(l) && !old.has(l.replace(/L\d+/, ""))).map((l) => l.trim())); // 只列這次新增的警告
    }
    const d = this.preview.createDiv();
    d.createEl("b", { text: "模擬寫入結果（還沒寫入）" });
    d.createEl("pre", { text: lines.length ? lines.join("\n") : "日期都照上表，沒有順延，也沒有新的警告" });
    return ok;
  }

  async write() {
    if (!this.ops) return;
    this.writeBtn.setDisabled(true);
    const out = [];
    for (const o of this.ops) {
      const r = await this.py(o.args);
      out.push(`${r.ok ? "✅" : "❌"} ${o.say}\n${r.text}`);
      if (!r.ok) { out.push("⚠️ 後面的項目沒有寫入（前面已寫入的保留）"); break; }
    }
    this.preview.empty();
    this.preview.createEl("pre", { text: out.join("\n\n") });
    this.status.setText(out.every((x) => x.startsWith("✅")) ? "已寫入 agenda" : "有項目沒寫入，看上面的訊息");
    this.ops = null;
    this.input.value = "";
  }
}

const toolLabel = (c) => c.name === "search_wiki" ? `搜尋「${c.input.query}」${c.input.path ? "（" + c.input.path + "）" : ""}`
  : c.name === "read_page" ? `讀 ${c.input.path}${c.input.offset ? " L" + c.input.offset : ""}`
  : c.name === "list_dir" ? `列出 ${c.input.path}` : `查 log ${JSON.stringify(c.input)}`;

/* 筆記所屬產品：frontmatter product: 優先，否則看路徑裡有沒有 wiki/concepts/ 下的產品資料夾名 */
function productOf(app, f) {
  if (!f) return "";
  const fm = (app.metadataCache.getFileCache(f) || {}).frontmatter || {};
  const p = [].concat(fm.product || fm.products || []).join(",");
  if (p) return p;
  const dir = app.vault.getAbstractFileByPath("wiki/concepts");
  const names = dir && dir.children ? dir.children.filter((c) => c.children && c.name !== "shared").map((c) => c.name) : [];
  return f.path.split("/").find((seg) => names.includes(seg)) || "";
}

/* 解釋用：選取文字含公司同仁姓名 → 通訊錄（email-roster.md「姓名｜信箱」表）＋角色（people.md 以 email 對應）
 * 10-19 實踩：選了使用者自己的名字，AI 查無資料就猜「可能是同事」 */
async function personContext(app) {
  const read = async (p) => { const f = app.vault.getAbstractFileByPath(p); return f ? app.vault.cachedRead(f) : ""; };
  const rows = (s) => s.split("\n").filter((l) => l.startsWith("|")).map((l) => l.split("|").slice(1, -1).map((c) => c.trim()));
  const roles = new Map(rows(await read("wiki/meta/people.md")).filter((r) => r[0].includes("@")).map((r) => [r[0].replace(/`/g, ""), r[1]]));
  return rows(await read("wiki/meta/email-roster.md")).filter((r) => r[1] && r[1].includes("@")).map(([name, email]) => ({ name, email, role: roles.get(email) || "" }));
}

/* 快取：PDF 換版（內容變）自動失效；source.txt 記最後一次的 vault 路徑，給人看是哪份 */
class Cache {
  constructor(dir) { this.dir = nodePath.join(dir, "cache"); }
  file(id, n) { return nodePath.join(this.dir, id, String(n).padStart(3, "0") + ".md"); }
  get(id, n) { try { return fs.readFileSync(this.file(id, n), "utf8"); } catch { return undefined; } }
  set(id, path, n, text) {
    fs.mkdirSync(nodePath.join(this.dir, id), { recursive: true });
    fs.writeFileSync(nodePath.join(this.dir, id, "source.txt"), path + "\n");
    fs.writeFileSync(this.file(id, n), text);
  }
}

class ConfirmModal extends Modal {
  constructor(app, text, onOk) { super(app); this.text = text; this.onOk = onOk; }
  onOpen() {
    this.contentEl.createEl("p", { text: this.text });
    new Setting(this.contentEl)
      .addButton((b) => b.setButtonText("開始").setCta().onClick(() => { this.close(); this.onOk(); }))
      .addButton((b) => b.setButtonText("取消").onClick(() => this.close()));
  }
}

class TranslateView extends ItemView {
  constructor(leaf, plugin) { super(leaf); this.plugin = plugin; this.raw = ""; }
  getViewType() { return VIEW; }
  getDisplayText() { return "AI 助手"; }
  getIcon() { return "languages"; }
  async onOpen() {
    const c = this.contentEl;
    c.empty(); c.addClass("pdf-translate");
    // 三排（使用者 10-19「改成 2-3 排比較方便看」）：標題／PDF 按鈕／問 wiki＋日程
    this.titleEl = c.createDiv("pt-title");
    const bar = c.createDiv("pt-bar");
    const auto = bar.createEl("button");
    const label = () => { auto.setText(this.plugin.auto ? "自動翻譯：開" : "自動翻譯：關"); auto.toggleClass("mod-cta", this.plugin.auto); };
    auto.onclick = () => { this.plugin.setAuto(!this.plugin.auto); label(); };
    label();
    bar.createEl("button", { text: "翻這頁" }).onclick = () => this.plugin.show(true);
    this.bookBtn = bar.createEl("button", { text: "翻整本" });
    this.bookBtn.onclick = () => this.plugin.book();
    bar.createEl("button", { text: "複製" }).onclick = () => navigator.clipboard.writeText(this.raw);
    bar.createEl("button", { text: "並排" }).onclick = () => this.plugin.sideBySide();
    const askRow = c.createDiv("pt-ask");
    this.askEl = askRow.createEl("input", { type: "text", placeholder: "問 wiki（例：產品 A 的輸出規格？／這頁在說什麼？）" });
    const go = () => { const q = this.askEl.value.trim(); if (q) this.plugin.ask(q); };
    this.askEl.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.isComposing) go(); }); // isComposing：注音選字的 Enter 不送出
    askRow.createEl("button", { text: "問" }).onclick = go;    if (this.plugin.hasAgenda) askRow.createEl("button", { text: "📅 日程" }).onclick = () => new AgendaModal(this.app, this.plugin).open();
    this.bookEl = c.createDiv("pt-status");
    this.statusEl = c.createDiv("pt-status");
    this.bodyEl = c.createDiv("pt-body");
    this.bodyEl.addEventListener("click", (e) => {
      const a = e.target.closest("a.internal-link");
      if (!a) return;
      e.preventDefault();
      this.app.workspace.openLinkText(a.getAttribute("data-href"), this.srcPath || "", true);
    });
    this.bodyEl.addEventListener("scroll", () => this.plugin.syncFromBody());
    // 譯文已捲到頭／尾還繼續滾 → 直接捲 PDF，翻到下一頁時譯文自動換頁
    this.bodyEl.addEventListener("wheel", (e) => {
      const b = this.bodyEl, end = b.scrollTop + b.clientHeight >= b.scrollHeight - 2;
      if ((e.deltaY > 0 && end) || (e.deltaY < 0 && b.scrollTop <= 0)) this.plugin.wheelPdf(e.deltaY);
    }, { passive: true });
    this.titleEl.setText("打開 PDF 會翻譯；選取文字按右鍵可翻譯／解釋");
    this.plugin.curKey = null;
    this.plugin.paintBook();
  }
  async put(title, status, md, done, sourcePath) {
    this.titleEl.setText(title);
    this.statusEl.setText(status);
    this.raw = stripMarks(md);
    this.srcPath = sourcePath;
    this.bodyEl.empty();
    this.bodyEl.toggleClass("pt-streaming", !done);
    const seq = (this.seq = (this.seq || 0) + 1);
    this.layout = null; this.lastPut = null;
    const pl = this.plugin, st = pl.state;
    if (done && md && /<!--b:\d{1,4}-->/.test(md) && pl.mode === "pdf" && st && st.kind !== "image") {
      this.lastPut = [title, status, md, done, sourcePath];
      this.segs = null;
      try { await pl.renderLayout(this, md, seq); return; }
      catch (e) { if (seq !== this.seq) return; this.statusEl.setText(status + "・版面對照失敗，改用文章式：" + e.message); }
    }
    const segs = done && md ? segments(md) : null;
    if (segs) for (const s of segs) {
      const d = this.bodyEl.createDiv("pt-seg");
      d.dataset.y0 = s.y; d.dataset.y1 = s.y1;
      await MarkdownRenderer.render(this.app, s.md, d, sourcePath, this);
    }
    else if (done && md) await MarkdownRenderer.render(this.app, this.raw, this.bodyEl, sourcePath, this);
    else this.bodyEl.setText(this.raw);
    this.segs = segs ? [...this.bodyEl.querySelectorAll(".pt-seg")] : null;
    this.segSig = null;
    if (done) this.plugin.syncFromPdf();
  }
}

module.exports = class PdfTranslate extends Plugin {
  async onload() {
    const dir = nodePath.join(this.app.vault.adapter.basePath, this.manifest.dir);
    this.cache = new Cache(dir);
    this.glossary = nodePath.join(dir, "glossary.txt");
    // vault 自己的補充規則（安裝／更新模組不覆蓋）：{ "ask": "接在問 wiki 系統提示後", "<ASSIST 鍵>": "接在該動作系統提示後" }
    try { this.local = JSON.parse(fs.readFileSync(nodePath.join(dir, "local-rules.json"), "utf8")); } catch { this.local = {}; }
    loadConn(dir);
    this.inflight = new Map();
    this.hashes = new Map();
    try { this.auto = localStorage.getItem(LS_AUTO) === "1"; } catch { this.auto = false; }
    this.onPdfScroll = () => this.syncFromPdf();
    this.register(() => this.watchPdf(null));
    this.registerView(VIEW, (leaf) => new TranslateView(leaf, this));
    this.addRibbonIcon("languages", "PDF 翻譯側欄", () => this.open());
    this.addCommand({ id: "open", name: "開啟 PDF 翻譯側欄", callback: () => this.open() });
    // 日程只在有 scripts/agenda.py＋wiki/agenda.md 的 vault 出現（沒有的 vault 不顯示）
    this.hasAgenda = ["scripts/agenda.py", "wiki/agenda.md"].every((f) => fs.existsSync(nodePath.join(this.app.vault.adapter.basePath, f)));
    if (this.hasAgenda) this.addCommand({ id: "agenda", name: "日程輔助（口述加會議／改期）", callback: () => new AgendaModal(this.app, this).open() });
    this.addCommand({ id: "ask", name: "問 wiki", callback: async () => { await this.open(); const v = this.view(); if (v) v.askEl.focus(); } });
    this.registerInterval(window.setInterval(() => this.tick(), 400));
    for (const [k, a] of Object.entries(ASSIST))
      this.addCommand({ id: "assist-" + k, name: `選取文字：${a.title}`, callback: () => this.assist(k, ...this.selection()) });
    this.registerEvent(this.app.workspace.on("editor-menu", (menu, editor) => {
      const sel = editor.getSelection();
      if (!sel.trim()) return;
      const target = this.target(editor);
      menu.addSeparator();
      for (const [k, a] of Object.entries(ASSIST))
        menu.addItem((i) => i.setTitle(`AI ${a.title}`).setIcon("sparkles").onClick(() => this.assist(k, sel, target)));
    }));
  }

  /* 改寫要取代回原處：記下選取範圍與原文，回來時原文沒被動過才取代 */
  target(editor) { return { editor, from: editor.getCursor("from"), to: editor.getCursor("to"), orig: editor.getSelection() }; }

  /* 編輯模式取 editor 選取（附取代目標）；閱讀模式與 PDF 取頁面選取 */
  selection() {
    const ed = this.app.workspace.activeEditor && this.app.workspace.activeEditor.editor;
    if (ed && ed.getSelection()) return [ed.getSelection(), this.target(ed)];
    return [String(window.getSelection() || ""), null];
  }

  async assist(kind, text, target) {
    const a = ASSIST[kind];
    text = (text || "").trim();
    if (!text) return new Notice("先選取一段文字");
    const src = this.app.workspace.getActiveFile(), product = productOf(this.app, src);
    await this.open();
    const v = this.view();
    if (!v) return;
    const s = this.pdfState();
    if (s) { this.curKey = s.file.path + "#" + s.page; this.state = s; } // 結果留著，翻頁才換回 PDF 譯文
    this.assistKey = s ? this.curKey : null;
    this.mode = "assist";
    if (a.ask) {
      const people = (await personContext(this.app)).filter((p) => p.name && text.includes(p.name));
      const dir = people.length ? `\n\n通訊錄（wiki/meta/email-roster.md）查到這些同仁：\n${people.map((p) => `- ${p.name}｜${p.email}${p.role ? "｜角色：" + p.role : ""}`).join("\n")}` : "";
      return this.ask(`請解釋「${text}」：先一句話講它是什麼，再講在我們產品裡的意義或用途，需要時舉例。` +
        `\n目前筆記：${src ? src.path : "（無）"}；目標產品＝目前筆記的產品：${product || "未標（不限產品，命中哪個產品要講明）"}。${dir}`,
        { title: `解釋：${text.length > 30 ? text.slice(0, 30) + "…" : text}`, path: src ? src.path : "",
          rules: "\n\n## 解釋模式補充\n- wiki 沒涵蓋的部分可用一般知識補充，但要標「[⚠️ 非資料庫：一般知識]」。\n- 有提供通訊錄資料＝公司同仁：只依那份資料說明姓名、email、角色。\n- 看起來是人名但通訊錄與 wiki 都查無 → 直說「通訊錄與 wiki 查無此人資料」，不推測他是誰、和誰什麼關係。" });
    }
    const user = text;
    const title = `${a.title}：${text.length > 30 ? text.slice(0, 30) + "…" : text}`, path = src ? src.path : "";
    const paint = (status, md, done) => { if (this.mode === "assist") v.put(title, status, md, done, path); };
    paint("處理中…", "", false);
    this.assisting = true;
    try {
      const t0 = Date.now();
      const { text: out, usage } = await translate([{ type: "text", text: user }], a.system + (this.local[kind] ? "\n" + this.local[kind] : ""), (t) => paint("處理中…", t, false));
      const done = `完成 ${((Date.now() - t0) / 1000).toFixed(1)} 秒・輸入 ${usage.in}／輸出 ${usage.out} tokens${money(usage.in, usage.out)}`;
      if (!a.replace || !target) return paint(done, out, true);
      // 改寫：結果換掉選取文字（使用者 10-18「把我們框的那一段換掉」）；型號提醒只放側欄，側欄留原文可對照
      const [body, ...note] = out.split(/\n-{3,}\n/);
      const ed = target.editor, keep = target.orig.match(/^\s*/)[0], tail = target.orig.match(/\s*$/)[0];
      if (ed.getRange(target.from, target.to) !== target.orig) return paint(done + "・⚠️ 選取處在等待時被改過，沒有取代；結果如下", out, true);
      ed.replaceRange(keep + body.trim() + tail, target.from, target.to);
      paint(done + "・已取代選取文字（Ctrl+Z 可復原）", (note.length ? note.join("\n").trim() + "\n\n" : "") + "**原文：**\n\n" + target.orig.trim(), true);
    } catch (e) { paint("❌ " + e.message, "", false); }
    finally { this.assisting = false; }
  }

  tool(name, input) { return runTool(this.app, name, input); } // 除錯用：不花錢直接試查詢工具

  /* 主編輯區最近用的分頁是 .md 筆記才回傳（使用者 10-19「.md 檔也要可以用」） */
  noteState() {
    const v = this.app.workspace.getMostRecentLeaf()?.view;
    return v && v.getViewType() === "markdown" && v.file ? { file: v.file, kind: "note", view: v } : null;
  }

  /* 「這頁在說什麼」（使用者 10-19）：附上正在看的那頁；有文字層送純文字（便宜），掃描頁才畫成圖；
     筆記短就送全文，長就只送畫面附近 NOTE_MAX 字（每輪都會重送，整篇長文很快吃到每題上限） */
  async pageAttach(s) {
    if (s.kind === "note") {
      const all = await this.app.vault.cachedRead(s.file);
      if (all.length <= NOTE_MAX) return [{ type: "text", text: `使用者正在看筆記「${s.file.path}」，全文如下：\n\n${all}` }];
      const lines = all.split("\n"), mode = s.view.currentMode;
      const top = Math.max(0, Math.floor((mode && mode.getScroll ? mode.getScroll() : 0) || 0) - 20);
      let end = top, size = 0;
      while (end < lines.length && size + lines[end].length <= NOTE_MAX) size += lines[end++].length + 1;
      if (end === top) end = top + 1;
      let start = top; // 捲到尾端時下面不夠，往上補滿
      while (start > 0 && size + lines[start - 1].length <= NOTE_MAX) size += lines[--start].length + 1;
      return [{ type: "text", text: `使用者正在看筆記「${s.file.path}」（全文 ${lines.length} 行太長，只附畫面附近第 ${start + 1}–${end} 行）：\n\n${lines.slice(start, end).join("\n")}` }];
    }
    const head = { type: "text", text: `使用者正在看「${s.file.basename}」第 ${s.page}／${s.total} 頁，內容如下：` };
    if (s.kind === "image") return [head, (await imageContent(this.app, s.file))[0]];
    const { blocks } = await pageBlocks(await this.freshDoc(s.file).getPage(s.page));
    const text = blocks.map((b) => b.text).join("\n");
    if (text.replace(/\s/g, "").length >= MIN_TEXT) return [head, { type: "text", text }];
    return [head, (await pageContent(this.freshDoc(s.file), s.page)).content[0]];
  }

  /* 問 wiki：Claude 用 TOOLS 一輪一輪查，最多 MAX_ROUNDS 輪；最後一輪禁用工具逼它依現有資料作答 */
  async ask(question, opts = {}) {
    if (this.asking) return new Notice("上一個問題還在查，請稍等");
    await this.open();
    const v = this.view();
    if (!v) return;
    const s = this.pdfState(), cur = s || this.noteState();
    const usePage = cur && PAGE_RE.test(question);
    if (s) { this.curKey = s.file.path + "#" + s.page; this.state = s; }
    this.assistKey = s ? this.curKey : null;
    this.mode = "assist";
    const short = question.length > 30 ? question.slice(0, 30) + "…" : question;
    const where = !usePage ? "" : s ? `這頁（第 ${s.page} 頁）` : `這篇（${cur.file.basename}）`;
    const title = opts.title || (usePage ? `${where}：${short}` : `問 wiki：${short}`), path = opts.path || (usePage ? cur.file.path : "");
    const paint = (status, md, done) => { if (this.mode === "assist") v.put(title, status, md, done, path); };
    const pdir = this.app.vault.getAbstractFileByPath("wiki/products");
    const products = pdir && pdir.children ? pdir.children.filter((c) => c.extension === "md").map((c) => c.basename).join("、") : "（讀不到 wiki/products/）";
    const system = ASK_SYSTEM(products) + (this.local.ask ? "\n" + this.local.ask : "") + (opts.rules || "") + (usePage ? PAGE_RULES : "");
    const messages = [{ role: "user", content: question }], steps = [];
    let tin = 0, tout = 0, answer = "";
    const t0 = Date.now(), trail = () => steps.map((x) => "- " + x).join("\n");
    this.asking = true;
    try {
      paint(usePage ? "讀這頁…" : "查詢中…", "", false);
      if (usePage) messages[0].content = [...await this.pageAttach(cur), { type: "text", text: question }];
      let capped = false;
      for (let round = 1; round <= MAX_ROUNDS; round++) {
        const last = round === MAX_ROUNDS || capped;
        const r = await chat({ system, tools: TOOLS, tool_choice: last ? { type: "none" } : { type: "auto" }, messages },
          (t) => paint(`第 ${round} 輪…`, (steps.length ? trail() + "\n\n" : "") + t, false));
        tin += r.usage.in; tout += r.usage.out;
        messages.push({ role: "assistant", content: r.blocks });
        const calls = r.blocks.filter((b) => b.type === "tool_use");
        if (!calls.length) { answer = r.text; break; }
        const results = [];
        for (const c of calls) {
          steps.push(toolLabel(c));
          paint(`第 ${round} 輪：查詢中…`, trail(), false);
          let out;
          try { out = await runTool(this.app, c.name, c.input || {}); } catch (e) { out = "錯誤：" + e.message; }
          results.push({ type: "tool_result", tool_use_id: c.id, content: out });
        }
        capped = tin + tout > ASK_TOKEN_CAP;
        if (capped) steps.push(`⚠️ 已用 ${tin + tout} tokens，超過每題上限 ${ASK_TOKEN_CAP}，停止查詢`);
        if (capped || round === MAX_ROUNDS - 1) results.push({ type: "text", text: "已達查詢上限：不要再呼叫工具，依目前查到的資料作答，並說明還有哪些沒查到。" });
        messages.push({ role: "user", content: results });
      }
      const done = `完成 ${((Date.now() - t0) / 1000).toFixed(1)} 秒・查了 ${steps.length} 次・輸入 ${tin}／輸出 ${tout} tokens${money(tin, tout)}`;
      paint(done, answer + (steps.length ? `\n\n> [!note]- 查詢過程（${steps.length} 次）\n${steps.map((x) => "> - " + x).join("\n")}` : ""), true);
    } catch (e) { paint("❌ " + e.message, trail(), false); }
    finally { this.asking = false; }
  }

  /* PDF 內容 hash；同一檔（路徑＋大小＋修改時間）只算一次 */
  docId(f) {
    const k = f.path + "|" + f.stat.size + "|" + f.stat.mtime;
    if (!this.hashes.has(k)) {
      const buf = fs.readFileSync(nodePath.join(this.app.vault.adapter.basePath, f.path));
      this.hashes.set(k, crypto.createHash("sha1").update(buf).digest("hex").slice(0, 16));
    }
    return this.hashes.get(k);
  }

  setAuto(on) {
    this.auto = on;
    try { localStorage.setItem(LS_AUTO, on ? "1" : "0"); } catch {}
    this.curKey = null; // 重新判斷目前頁：剛打開就開始翻
  }

  /* 跟隨捲動：譯文只有目前這一頁，所以按「頁內比例」對齊；對方程式捲動觸發的 scroll 在 120ms 內忽略，免得互相拉扯 */
  syncCtx() {
    const v = this.view(), s = this.state;
    if (!v || this.mode !== "pdf" || !s || s.kind === "image") return null;
    const pv = this.viewerOf(s.file);
    if (!pv || !pv.container || pv.currentPageNumber !== s.page) return null;
    const pg = pv.getPageView && pv.getPageView(s.page - 1);
    if (!pg || !pg.div) return null;
    const c = pv.container, pr = pg.div.getBoundingClientRect(), cr = c.getBoundingClientRect();
    const top = pr.top - cr.top + c.scrollTop + pg.div.clientTop, left = pr.left - cr.left + c.scrollLeft + pg.div.clientLeft;
    return { v, b: v.bodyEl, c, pg, top, left, h: Math.max(1, pg.div.offsetHeight), span: Math.max(1, pg.div.offsetHeight - c.clientHeight) };
  }
  syncFromPdf() {
    if (Date.now() < this.quietPdf) return;
    const x = this.syncCtx();
    if (!x) return;
    if (x.v.layout) { // 版面對照：右邊是同尺寸的譯文頁，捲動位置一比一
      this.quietBody = Date.now() + 120;
      x.b.scrollTop = x.c.scrollTop - x.top;
      x.b.scrollLeft = x.c.scrollLeft - x.left;
      return;
    }
    if (x.v.segs) { // 有對位標記：標亮和 PDF 可見範圍重疊的段並捲過去（10-19 使用者：藏起來會像譯文消失，改成全留＋標亮）
      const v0 = (x.c.scrollTop - x.top) / x.h * 100, v1 = (x.c.scrollTop + x.c.clientHeight - x.top) / x.h * 100;
      const on = x.v.segs.filter((d) => +d.dataset.y0 < v1 && +d.dataset.y1 > v0);
      const all = !on.length || on.length === x.v.segs.length; // 整頁都看得到就不標
      const sig = all ? "" : on.map((d) => d.dataset.y0).join(",");
      if (sig === x.v.segSig) return; // 可見段沒變就不動，使用者可以自己捲右邊
      x.v.segSig = sig;
      x.v.segs.forEach((d) => d.toggleClass("pt-on", !all && on.includes(d)));
      if (!all) { this.quietBody = Date.now() + 120; x.b.scrollTop += on[0].getBoundingClientRect().top - x.b.getBoundingClientRect().top - 8; }
      return;
    }
    const f = Math.min(1, Math.max(0, (x.c.scrollTop - x.top) / x.span));
    this.quietBody = Date.now() + 120;
    x.b.scrollTop = f * (x.b.scrollHeight - x.b.clientHeight);
  }
  syncFromBody() {
    if (Date.now() < this.quietBody) return;
    const x = this.syncCtx();
    if (x && x.v.layout) {
      this.quietPdf = Date.now() + 120;
      x.c.scrollTop = x.top + x.b.scrollTop;
      x.c.scrollLeft = x.left + x.b.scrollLeft;
      return;
    }
    if (!x || x.v.segs || x.b.scrollHeight <= x.b.clientHeight) return; // 逐段模式由 PDF 主導
    this.quietPdf = Date.now() + 120;
    x.c.scrollTop = x.top + x.b.scrollTop / (x.b.scrollHeight - x.b.clientHeight) * x.span;
  }
  wheelPdf(dy) {
    const x = this.syncCtx();
    if (x) x.c.scrollTop += dy;
  }
  /* PDF 捲動監聽掛在目前那份 PDF 的捲動容器上；換檔就換掛 */
  watchPdf(c) {
    if (c === this.watched) return;
    if (this.watched) this.watched.removeEventListener("scroll", this.onPdfScroll);
    this.watched = c;
    if (c) c.addEventListener("scroll", this.onPdfScroll, { passive: true });
  }

  viewerOf(file) {
    const l = this.app.workspace.getLeavesOfType("pdf").find((l) => l.view.file && l.view.file.path === file.path);
    return l && l.view.viewer && l.view.viewer.child && l.view.viewer.child.pdfViewer && l.view.viewer.child.pdfViewer.pdfViewer;
  }

  /* 版面對照畫面：原頁畫成底圖，每塊譯文蓋在原文位置，字級縮到塞得進原框；尺寸跟左邊 PDF 目前縮放一樣 */
  async renderLayout(v, md, seq) {
    const s = this.state, page = await this.freshDoc(s.file).getPage(s.page);
    const { W, H, blocks } = await pageBlocks(page);
    const tr = new Map(), parts = md.split(/<!--b:(\d{1,4})-->/);
    for (let i = 1; i < parts.length; i += 2) tr.set(+parts[i], parts[i + 1].trim());
    const pv = this.viewerOf(s.file), pg = pv && pv.getPageView && pv.getPageView(s.page - 1);
    const k = pg && pg.viewport ? pg.viewport.width / W : Math.max(200, v.bodyEl.clientWidth - 12) / W;
    const dpr = window.devicePixelRatio || 1, vp = page.getViewport({ scale: k * dpr });
    const cv = document.createElement("canvas");
    cv.width = vp.width; cv.height = vp.height;
    const g = cv.getContext("2d", { willReadFrequently: true });
    await page.render({ canvasContext: g, viewport: vp }).promise;
    if (seq !== v.seq) return;
    const box = v.bodyEl.createDiv("pt-layout");
    box.style.width = W * k + "px"; box.style.height = H * k + "px";
    cv.style.width = W * k + "px"; cv.style.height = H * k + "px";
    box.appendChild(cv);
    for (const b of blocks) {
      const t = tr.get(b.id);
      if (!t) continue;
      const d = box.createDiv({ cls: "pt-box", text: t });
      Object.assign(d.style, { left: b.x * k - 1 + "px", top: b.y * k - 1 + "px", width: b.w * k + 4 + "px", height: b.h * k + 2 + "px" }); // 高度固定＝整個原文框，底下的英文才蓋得掉
      const bg = bgAt(g, (b.x * k - 2) * dpr, (b.y * k - 2) * dpr, (b.w * k + 6) * dpr, (b.h * k + 4) * dpr); // 遮罩取原頁底色（紅標題列、灰底不要變白框）
      if (bg) { d.style.background = `rgb(${bg})`; d.style.color = bg[0] * 0.3 + bg[1] * 0.59 + bg[2] * 0.11 < 140 ? "#fff" : "#111"; }
      let f = b.fs * k * 0.9;
      d.style.fontSize = f + "px";
      while (d.scrollHeight > d.clientHeight + 1 && f > b.fs * k * 0.45) { f *= 0.9; d.style.fontSize = f + "px"; }
    }
    v.layout = { k, W };
    this.syncFromPdf();
  }

  /* 並排：把 AI 助手搬到 PDF 右邊的主編輯區分割，和 PDF 一樣大，版面對照才看得清楚 */
  async sideBySide() {
    const s = this.pdfState();
    const pdf = s && this.app.workspace.getLeavesOfType("pdf").find((l) => l.view.file && l.view.file.path === s.file.path);
    if (!pdf) return this.noPdf("並排");
    const old = this.app.workspace.getLeavesOfType(VIEW);
    const l = this.app.workspace.createLeafBySplit(pdf, "vertical");
    await l.setViewState({ type: VIEW, active: false });
    old.forEach((o) => o.detach());
    this.state = s; this.curKey = null;
  }

  view() { const l = this.app.workspace.getLeavesOfType(VIEW)[0]; return l && l.view instanceof TranslateView ? l.view : null; }

  async open() {
    let l = this.app.workspace.getLeavesOfType(VIEW)[0];
    if (!l) { l = this.app.workspace.getRightLeaf(false); await l.setViewState({ type: VIEW, active: true }); }
    this.app.workspace.revealLeaf(l);
  }

  /* 主編輯區最近用的分頁是 PDF 才回傳；焦點在側欄時也找得到 */
  pdfState() {
    let leaf = this.app.workspace.getMostRecentLeaf();
    if (leaf && leaf.view.getViewType() === VIEW) // 並排時焦點在 AI 助手分頁 → 沿用正在跟的那份 PDF
      leaf = this.state && this.app.workspace.getLeavesOfType("pdf").find((l) => l.view.file && l.view.file.path === this.state.file.path);
    const v = leaf && leaf.view;
    if (v && v.getViewType() === "image" && v.file && IMG_EXT.includes(v.file.extension.toLowerCase()))
      return { file: v.file, kind: "image", page: 1, total: 1 };
    const pv = v && v.getViewType() === "pdf" && v.viewer && v.viewer.child && v.viewer.child.pdfViewer && v.viewer.child.pdfViewer.pdfViewer;
    if (!pv || !pv.pdfDocument || !v.file) return null;
    return { file: v.file, doc: pv.pdfDocument, pv, page: pv.currentPageNumber, total: pv.pdfDocument.numPages };
  }

  /* 讀頁當下才向檢視器拿 pdfDocument：PDF 分頁重載後舊物件已銷毀（10-18 實踩 reading 'sendWithPromise'） */
  freshDoc(file) {
    for (const l of this.app.workspace.getLeavesOfType("pdf")) {
      const v = l.view, pv = v.file && v.file.path === file.path && v.viewer && v.viewer.child && v.viewer.child.pdfViewer && v.viewer.child.pdfViewer.pdfViewer;
      if (pv && pv.pdfDocument) return pv.pdfDocument;
    }
    throw new Error("這份 PDF 已經關閉，打開它再翻");
  }

  system(base = SYSTEM) {
    let g = "";
    try { g = fs.readFileSync(this.glossary, "utf8").trim(); } catch {}
    return g ? `${base}\n\n術語表（一律照這個翻）：\n${g}` : base;
  }

  isCur(id, n) { return this.state && this.docId(this.state.file) === id && this.state.page === n; }
  title(s) { return s.kind === "image" ? `${s.file.name}（圖片）` : `${s.file.basename}　第 ${s.page}／${s.total} 頁`; }

  tick() {
    const v = this.view();
    if (!v) return;
    const s = this.pdfState();
    if (!s) return; // 切到非 PDF 分頁就留著上一頁的譯文
    this.watchPdf(s.pv ? s.pv.container : null);
    const key = s.file.path + "#" + s.page;
    if (key === this.curKey) {
      if (v.segs) this.syncFromPdf();
      const pg = v.layout && s.pv && s.pv.getPageView && s.pv.getPageView(s.page - 1);
      if (pg && pg.viewport && Math.abs(pg.viewport.width / v.layout.W / v.layout.k - 1) > 0.03 && v.lastPut) v.put(...v.lastPut); // 左邊縮放了 → 照新尺寸重畫
      return;
    } // 縮放不一定觸發 scroll，逐段模式每拍補對一次
    if (this.mode === "assist") { // 10-19 實踩：查詢途中點到 PDF，答案被 PDF 畫面蓋掉
      if (this.asking || this.assisting) return;
      if (this.assistKey === null) { this.assistKey = this.curKey = key; this.state = s; return; }
    }
    this.curKey = key; this.state = s; this.mode = "pdf";
    clearTimeout(this.timer);
    const hit = this.cache.get(this.docId(s.file), s.page);
    if (hit) return v.put(this.title(s), /<!--b:\d/.test(hit) ? "快取・版面對照" : MARK.test(hit) ? "快取" : "快取・舊譯文；按「翻這頁」重翻可版面對照", hit, true, s.file.path);
    if (!this.auto) return v.put(this.title(s), "自動翻譯已關閉；要翻這頁按「翻這頁」", "", false);
    v.put(this.title(s), "等待翻譯…", "", false);
    this.timer = setTimeout(() => this.show(), DEBOUNCE);
  }

  async show(force) {
    const cur = this.pdfState();
    if (cur) this.state = cur;
    else if (force) return this.noPdf("翻這頁"); // 按鈕觸發時目前分頁不是 PDF，不拿上一份 PDF 去翻（使用者 10-19）
    const s = this.state, v = this.view();
    if (!s || !v) return;
    const id = this.docId(s.file), n = s.page;
    this.mode = "pdf";
    try { await this.run(s, n, force); }
    catch (e) { if (this.isCur(id, n)) v.put(this.title(s), "❌ " + e.message, "", false); return; }
    if (this.auto && n < s.total && !this.cache.get(id, n + 1)) this.run(s, n + 1, false).catch(() => {});
  }

  noPdf(btn) {
    const msg = `目前分頁不是 PDF 或圖片：先打開（或點一下）要翻的檔，再按「${btn}」`;
    new Notice(msg);
    const v = this.view();
    if (v) v.statusEl.setText("⚠️ " + msg);
  }

  /* 翻整本：先確認頁數，背景一頁一頁翻（已翻的跳過），再按一次＝停止 */
  book() {
    if (this.bookJob) { this.bookJob.stop = true; return; }
    const s = this.pdfState();
    if (!s) return this.noPdf("翻整本");
    if (s.kind === "image") return new Notice("圖片只有一頁，按「翻這頁」就好");
    this.state = s;
    const id = this.docId(s.file), todo = [];
    for (let n = 1; n <= s.total; n++) if (!this.cache.get(id, n)) todo.push(n);
    if (!todo.length) return new Notice("這份已經整本翻好了");
    try { headers(); } catch (e) { return new Notice(e.message); }
    // 粗估每頁輸入／輸出各 1,500 tokens（10-18 實測 3 頁介於 400–1,500）；圖多或掃描頁會更高
    const est = money(todo.length * 1500, todo.length * 1500).replace(/^・/, "");
    new ConfirmModal(this.app, `「${s.file.basename}」共 ${s.total} 頁，還有 ${todo.length} 頁沒翻。要在背景全部翻完嗎？粗估${est}（每頁以 3,000 tokens 估，實際依內容而定），翻到一半可按「停止整本」。`, () => this.runBook(s, todo)).open();
  }

  async runBook(s, todo) {
    const job = (this.bookJob = { stop: false, done: 0, total: todo.length, name: s.file.basename, tin: 0, tout: 0 });
    this.paintBook();
    for (const n of todo) {
      if (job.stop) break;
      try { const u = await this.run(s, n, false); if (u) { job.tin += u.in; job.tout += u.out; } }
      catch (e) { job.err = `整本翻譯在第 ${n} 頁停下：${e.message}`; break; }
      job.done++;
      this.paintBook();
    }
    this.bookJob = null;
    this.paintBook(job);
  }

  paintBook(last) {
    const v = this.view(), j = this.bookJob;
    if (!v || !v.bookEl) return;
    v.bookBtn.setText(j ? "停止整本" : "翻整本");
    const sum = (x) => `${x.tin + x.tout} tokens${money(x.tin, x.tout)}`;
    v.bookEl.setText(j ? `整本翻譯「${j.name}」：${j.done}／${j.total} 頁・${sum(j)}`
      : !last ? "" : last.err ? `❌ ${last.err}（已翻 ${last.done} 頁・${sum(last)}）`
      : `${last.stop ? "已停止" : "整本完成"}「${last.name}」：翻了 ${last.done}／${last.total} 頁・${sum(last)}`);
  }

  /* 同一頁同時只跑一次；不論是不是預翻，只要它剛好是目前頁就把串流畫上去 */
  run(s, n, force) {
    const id = this.docId(s.file), key = id + "#" + n;
    if (this.inflight.has(key)) return this.inflight.get(key);
    const paint = (status, md, done) => { const v = this.view(); if (v && this.mode !== "assist" && this.isCur(id, n)) v.put(this.title(this.state), status, md, done, s.file.path); };
    const p = (async () => {
      if (!force && this.cache.get(id, n)) return;
      paint("翻譯中…", "", false);
      const { content, layout } = s.kind === "image" ? { content: await imageContent(this.app, s.file) } : await pageContent(this.freshDoc(s.file), n);
      const t0 = Date.now();
      const { text, usage } = await translate(content, this.system(layout ? LAYOUT_SYSTEM : SYSTEM), (t) => paint("翻譯中…", t, false));
      this.cache.set(id, s.file.path, n, text);
      const img = s.kind === "image" ? "・圖片" : content[0].type === "image" ? "・掃描頁（送圖）" : "";
      paint(`完成 ${((Date.now() - t0) / 1000).toFixed(1)} 秒・輸入 ${usage.in}／輸出 ${usage.out} tokens${money(usage.in, usage.out)}${img}`, text, true);
      return usage;
    })().finally(() => this.inflight.delete(key));
    this.inflight.set(key, p);
    return p;
  }
};
