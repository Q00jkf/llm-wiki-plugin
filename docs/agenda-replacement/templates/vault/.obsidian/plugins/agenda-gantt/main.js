/* 日程甘特圖（agenda-gantt）—— llm-wiki 的 wiki/agenda.md 甘特圖視圖
 * 只做畫面：資料一律來自 `agenda.py --json`，不自行解析 agenda.md；
 * 寫回只走 agenda.py 指令（done／undone／move／dur／add／link／unlink；關鍵字用 json 的 match），寫完重讀 json（順延由引擎做）。
 * 重複事件不給打勾（done 會把整條規則停掉）。
 * agenda.py 位置：設定值 → vault 的 scripts/agenda.py → 已安裝的 llm-wiki plugin（~/.claude/plugins/installed_plugins.json）。
 * 免 build 手寫 CommonJS；設定存本機 localStorage，不寫 data.json（免得進 git）。
 */
const { Plugin, ItemView, PluginSettingTab, Setting, Notice, Modal } = require("obsidian");
const { execFile } = require("child_process");
const fs = require("fs");
const path = require("path");
const os = require("os");

const VIEW = "agenda-gantt";
const AGENDA = "wiki/agenda.md";
const DEFAULTS = { python: "python", script: "", file: "", before: 7, after: 60 };
const DW = 22, RH = 24, HH = 40, LW = 300; // 一天寬、列高、表頭高、標籤欄寬
const SVG = "http://www.w3.org/2000/svg";

const day = (s) => { const [y, m, d] = s.split("-").map(Number); return Date.UTC(y, m - 1, d) / 864e5; };
const iso = (n) => new Date(n * 864e5).toISOString().slice(0, 10);
const todayN = () => { const t = new Date(); return Date.UTC(t.getFullYear(), t.getMonth(), t.getDate()) / 864e5; };
const md = (n) => iso(n).slice(5).replace("-", "/");

function el(tag, attrs, parent) {
  const e = document.createElementNS(SVG, tag);
  for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}

class GanttView extends ItemView {
  constructor(leaf, plugin) { super(leaf); this.plugin = plugin; this.data = null; this.err = null; }
  getViewType() { return VIEW; }
  getDisplayText() { return "日程甘特圖"; }
  getIcon() { return "gantt-chart"; }

  async onOpen() {
    this.addAction("refresh-cw", "重新讀取", () => this.reload());
    this.registerDomEvent(window, "keydown", (ev) => { if (ev.key === "Escape" && this.linking) this.setLinking(false); });
    this.contentEl.addClass("ag-view");
    await this.reload();
  }

  async reload() {
    try { this.data = await this.plugin.fetch(); this.err = null; }
    catch (e) { this.err = String(e.message || e); }
    this.render();
  }

  render() {
    const c = this.contentEl;
    const keepX = this.scroller ? this.scroller.scrollLeft : null, keepY = this.scroller ? this.scroller.scrollTop : 0;
    c.empty();
    if (this.err) { c.createDiv({ cls: "ag-error", text: "讀取失敗：" + this.err }); return; }
    if (!this.data) { c.createDiv({ text: "讀取中…" }); return; }
    const d = this.data, s = this.plugin.settings, t0 = todayN();
    const w0 = t0 - s.before, w1 = t0 + s.after, W = (w1 - w0 + 1) * DW;
    const X = (n) => (n - w0) * DW;

    const top = c.createDiv({ cls: "ag-top" });
    const src = top.createSpan({ cls: "ag-src", text: `來源 ${d.source}｜產生 ${d.generated.replace("T", " ")}` });
    src.title = d.source;
    const tools = top.createSpan({ cls: "ag-tools" });
    tools.createEl("button", { text: "＋ 新增", attr: { title: "新增事項（agenda.py add）" } }).onclick = () => this.addEvent(null);
    const lk = tools.createEl("button", { text: this.linking ? "結束畫接" : "畫接", cls: this.linking ? "mod-cta" : "" });
    lk.title = "畫接：先點前項、再點後項；點連線＝拆接（Esc 結束）";
    lk.onclick = () => this.setLinking(!this.linking);
    if (this.linking) tools.createSpan({ cls: "ag-hint", text: this.linkFrom ? `前項：${this.linkFrom.title} → 點後項` : "點前項" });
    c.toggleClass("ag-linking", !!this.linking);
    const legend = top.createSpan({ cls: "ag-legend" });
    for (const [cls, txt] of [["ag-crit", "要徑"], ["ag-late", "逾期"], ["ag-done", "已完成"], ["ag-sum", "母項"], ["ag-basekey", "原定（改期前）"]])
      legend.createSpan({ cls: "ag-key " + cls, text: txt });
    for (const [k, list] of [["壞行", d.bad.map((b) => `第 ${b.line} 行：${b.text}`)], ["相依問題", d.problems]])
      if (list.length) c.createDiv({ cls: "ag-warn", text: `⚠️ ${k} ${list.length} 項（agenda.py --check）：` + list.join("；") });

    const rows = this.layout(d, w0, w1, t0);
    const H = rows.length * RH;
    const scroller = c.createDiv({ cls: "ag-scroll" });
    this.scroller = scroller;
    const inner = scroller.createDiv({ cls: "ag-inner" });
    inner.style.width = LW + W + "px";
    const left = inner.createDiv({ cls: "ag-left" });
    left.style.width = LW + "px";
    left.createDiv({ cls: "ag-corner" }).style.height = HH + "px";
    const right = inner.createDiv({ cls: "ag-right" });
    const head = el("svg", { width: W, height: HH, class: "ag-head" }, right);
    const body = el("svg", { width: W, height: H, class: "ag-body" }, right);
    el("defs", {}, body).innerHTML =
      '<marker id="ag-arrow" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L6,3 L0,6 z" class="ag-arrowhead"/></marker>';

    // 表頭與底色：週末／國定假日灰底、補班日不灰、今天紅線
    const cal = d.calendar || { off: {}, on: {} }, off = cal.off, on = cal.on;
    for (let n = w0; n <= w1; n++) {
      const date = iso(n), wd = new Date(n * 864e5).getUTCDay();
      const rest = (off[date] !== undefined) || ((wd === 0 || wd === 6) && on[date] === undefined);
      if (rest) {
        const r = el("rect", { x: X(n), y: 0, width: DW, height: H, class: off[date] ? "ag-holiday" : "ag-weekend" }, body);
        if (off[date]) el("title", {}, r).textContent = `${date} ${off[date]}`;
      }
      if (n === w0 || date.endsWith("-01"))
        el("text", { x: X(n) + 3, y: 14, class: "ag-month" }, head).textContent = date.slice(0, 7);
      const tx = el("text", { x: X(n) + DW / 2, y: 33, class: "ag-dnum" + (rest ? " ag-rest" : "") }, head);
      tx.textContent = String(Number(date.slice(8)));
      if (off[date]) el("title", {}, tx).textContent = off[date];
    }
    el("line", { x1: X(t0) + DW / 2, x2: X(t0) + DW / 2, y1: 0, y2: H, class: "ag-today" }, body);

    // 列
    const where = new Map(); // id → {x0, x1, y}
    rows.forEach((r, i) => {
      const y = i * RH;
      const lab = left.createDiv({ cls: "ag-label" + (r.kind === "sec" ? " ag-sec" : "") });
      lab.style.height = RH + "px";
      const inn = lab.createDiv({ cls: "ag-lab-in" }); // 標題欄自己的水平捲動只移這層
      if (r.kind === "sec") {
        inn.createSpan({ text: `${r.collapsed ? "▶" : "▼"} ${r.name}（${r.count}）` });
        const plus = inn.createSpan({ cls: "ag-secadd", text: "＋", attr: { title: `在「${r.name}」新增事項` } });
        plus.onclick = (ev) => { ev.stopPropagation(); this.addEvent(r.tag); };
        lab.onclick = () => this.plugin.toggle(r.name).then(() => this.render());
        el("rect", { x: 0, y, width: W, height: RH, class: "ag-secband" }, body);
        return;
      }
      const e = r.e;
      lab.style.paddingLeft = 6 + r.depth * 14 + "px";
      const cb = inn.createEl("input", { cls: "ag-cb", attr: { type: "checkbox" } });
      if (e.rule) { cb.disabled = true; cb.addClass("ag-cb-none"); }
      else if (e.done) { cb.checked = true; cb.title = "取消勾選＝改回未完成（agenda.py undone，拿掉 ✅ 與 完成:）"; }
      else cb.title = "打勾＝完成（agenda.py done，自動補 完成:今天）";
      cb.onclick = (ev) => {
        ev.stopPropagation();
        if (cb.disabled || this.busy) { ev.preventDefault(); return; }
        cb.disabled = true;
        if (e.done) this.write(["undone", e.match], `改回未完成：${e.title}`);
        else this.write(["done", e.match], `完成：${e.title}`);
      };
      inn.createSpan({ cls: "ag-type" + (e.hard ? " ag-hardtype" : ""), text: e.type });
      inn.createSpan({ text: (e.done ? "✓ " : "") + e.title });
      lab.title = e.match;
      lab.onclick = () => this.plugin.reveal(d.source, e.line);
      this.bar(body, r, y, X, w0, w1, t0, where);
    });

    this.labelScroll(left);

    // 接：前項→後項箭頭（兩端都畫出來才連）
    for (const r of rows) {
      if (r.kind !== "ev" || !r.e.links.length || !where.has(r.e.id)) continue;
      const b = where.get(r.e.id);
      for (const [code, type] of r.e.links) {
        const a = where.get(code);
        if (!a) continue;
        const sx = type === "SS" || type === "SF" ? a.x0 : a.x1, ex = type === "FF" || type === "SF" ? b.x1 : b.x0;
        const sy = a.y + RH / 2, ey = b.y + RH / 2, mx = sx + 6, dd = `M${sx},${sy} H${mx} V${ey} H${ex}`;
        const lg = el("g", { class: "ag-lk" }, body);
        el("path", { d: dd, class: "ag-link", "marker-end": "url(#ag-arrow)" }, lg);
        const hit = el("path", { d: dd, class: "ag-link-hit" }, lg); // 畫接模式才點得到：點了拆接
        el("title", {}, hit).textContent = `接:${code}（點一下拆掉）`;
        hit.addEventListener("click", () => this.unlinkAsk(a.e, r.e, code));
      }
    }
    if (keepX === null) scroller.scrollLeft = Math.max(0, X(t0) - 3 * DW);
    else { scroller.scrollLeft = keepX; scroller.scrollTop = keepY; }
  }

  /* 標題欄底部的水平捲軸：字比欄寬長時才出現；滑鼠在標題欄上 Shift＋滾輪（或觸控板左右滑）也能捲 */
  labelScroll(left) {
    const over = Math.max(0, ...[...left.querySelectorAll(".ag-lab-in")].map((x) => x.scrollWidth - x.clientWidth));
    if (!over) { this.labelX = 0; return; }
    const sb = left.createDiv({ cls: "ag-lscroll" });
    sb.createDiv({ cls: "ag-lscroll-in" }).style.width = LW + over + "px";
    const set = () => { this.labelX = sb.scrollLeft; left.style.setProperty("--ag-lx", sb.scrollLeft + "px"); };
    sb.addEventListener("scroll", set);
    sb.scrollLeft = Math.min(this.labelX || 0, over);
    set();
    left.addEventListener("wheel", (ev) => {
      const dx = ev.shiftKey ? ev.deltaY || ev.deltaX : Math.abs(ev.deltaX) > Math.abs(ev.deltaY) ? ev.deltaX : 0;
      if (!dx) return;
      sb.scrollLeft += dx;
      ev.preventDefault();
    }, { passive: false });
  }

  /* 左右拖整條：行首日期（完成日）平移 N 天，確認後 agenda.py move；接的後項由引擎順延 */
  /* 拉條右端改工期：開始日不動，完成日跟著變，確認後 agenda.py dur；接在完成日的後項一起平移 */
  resizable(g, barEl, e, sp, x1, y) {
    const h = el("rect", { x: x1 - 7, y: y + 4, width: 7, height: RH - 8, class: "ag-handle" }, g);
    el("title", {}, h).textContent = "拉右端改工期";
    h.addEventListener("click", (ev) => ev.stopPropagation());
    h.addEventListener("mousedown", (ev) => {
      if (ev.button !== 0 || this.busy || this.linking) return;
      ev.preventDefault();
      ev.stopPropagation(); // 不觸發整條平移
      const x0 = ev.clientX, w0 = Number(barEl.getAttribute("width"));
      let dd = 0;
      const mv = (m) => {
        dd = Math.max(day(e.start) - sp.f, Math.round((m.clientX - x0) / DW)); // 最短到開始日（1 天）
        barEl.setAttribute("width", Math.max(2, w0 + dd * DW));
        h.setAttribute("x", x1 - 7 + dd * DW);
      };
      const up = async () => {
        window.removeEventListener("mousemove", mv);
        window.removeEventListener("mouseup", up);
        const reset = () => { barEl.setAttribute("width", w0); h.setAttribute("x", x1 - 7); };
        if (!dd) return reset();
        this.dragged = true;
        setTimeout(() => (this.dragged = false), 0);
        const n = this.workdays(day(e.start), sp.f + dd);
        if (n === e.dur) return reset();
        const fin = this.addWork(day(e.start), n - 1);
        const lines = [`工期 ${e.dur} 天 → ${n} 天（工作天；開始日 ${md(day(e.start))} 不動）`, `完成日 ${md(day(e.date))} → ${md(fin)}`];
        if (e.hard) lines.push(`⚠️ ${e.type}是硬期限：完成日會改寫。確定？`);
        if (e.id && this.data.events.some((x) => x.links.some((l) => l[0] === e.id))) lines.push("接在完成日的後項會一起平移。");
        if (!(await this.plugin.confirm(`改工期：${e.title}`, lines, e.hard))) return reset();
        await this.write(["dur", e.match, String(n)], `改工期：${e.title} → ${n} 天`);
      };
      window.addEventListener("mousemove", mv);
      window.addEventListener("mouseup", up);
    });
  }

  isWork(n) {
    const cal = this.data.calendar || { off: {}, on: {} }, date = iso(n), wd = new Date(n * 864e5).getUTCDay();
    return cal.on[date] !== undefined || (wd !== 0 && wd !== 6 && cal.off[date] === undefined);
  }

  workdays(s, f) { // s～f（含）幾個工作天，至少 1
    let n = 0;
    for (let x = s; x <= f; x++) n += this.isWork(x) ? 1 : 0;
    return Math.max(1, n);
  }

  addWork(s, k) { // 同 agenda_cpm.Calendar.add（k≥0）
    let x = s;
    while (k > 0) { x++; if (this.isWork(x)) k--; }
    return x;
  }

  draggable(g, e) {
    g.classList.add("ag-drag");
    g.addEventListener("mousedown", (ev) => {
      if (ev.button !== 0 || this.busy || this.linking) return;
      ev.preventDefault();
      const x0 = ev.clientX;
      let dd = 0;
      const mv = (m) => { dd = Math.round((m.clientX - x0) / DW); g.setAttribute("transform", `translate(${dd * DW},0)`); };
      const up = async () => {
        window.removeEventListener("mousemove", mv);
        window.removeEventListener("mouseup", up);
        if (!dd) { g.removeAttribute("transform"); return; }
        this.dragged = true;
        setTimeout(() => (this.dragged = false), 0);
        const from = day(e.date), to = from + dd, date = iso(to), cal = this.data.calendar || { off: {}, on: {} };
        const wd = new Date(to * 864e5).getUTCDay();
        const lines = [`${md(from)} → ${md(to)}（${dd > 0 ? "延後" : "提前"} ${Math.abs(dd)} 天）`];
        if (cal.off[date]) lines.push(`⚠️ ${date} 是 ${cal.off[date]}（放假）`);
        else if ((wd === 0 || wd === 6) && cal.on[date] === undefined) lines.push(`⚠️ ${date} 是週${"日一二三四五六"[wd]}`);
        if (e.hard) lines.push(`⚠️ ${e.type}是硬期限：引擎從不替它改期。確定要改寫的日期？`);
        if (e.links.length && !e.hard) lines.push("有接前項：開始日不會早於前項完成，引擎可能再往後排。");
        if (e.id && this.data.events.some((x) => x.links.some((l) => l[0] === e.id))) lines.push("後項會由引擎自動順延。");
        if (!(await this.plugin.confirm(`改期：${e.title}`, lines, e.hard))) { g.removeAttribute("transform"); return; }
        await this.write(["move", e.match, date], `改期：${e.title} → ${md(to)}`);
      };
      window.addEventListener("mousemove", mv);
      window.addEventListener("mouseup", up);
    });
  }

  setLinking(on) { this.linking = on; this.linkFrom = null; this.render(); }

  /* 畫接：第一下選前項，第二下選後項 → 問類型／前置天數（前項沒代號再問代號）→ agenda.py link */
  async pick(e) {
    if (this.busy) return;
    if (!this.linkFrom) {
      if (e.rule) { new Notice("重複事件不支援接"); return; }
      this.linkFrom = e;
      return this.render();
    }
    const p = this.linkFrom;
    if (p.match === e.match) { this.linkFrom = null; return this.render(); } // 再點一次＝取消選取
    if (e.done || e.rule || (e.plan && e.plan.summary)) { new Notice(`「${e.title}」不能當後項（已完成／重複事件／母項）`); return; }
    if (e.links.some((l) => l[0] === p.id)) { new Notice("已經接了"); return; }
    const ans = await this.linkDialog(p, e);
    this.linkFrom = null;
    if (!ans) return this.render();
    const args = ["link", e.match, p.match, "--type", ans.type, `--lag=${ans.lag}`];
    if (!p.id) args.push("--id", ans.id);
    await this.write(args, `接上：${p.title} → ${e.title}`);
  }

  linkDialog(p, e) {
    return new Promise((ok) => {
      const m = new Modal(this.app), v = { type: "FS", lag: 0, id: "" };
      let res = null;
      m.titleEl.setText("畫接");
      m.contentEl.createEl("p", { text: `前項：${p.type} ${p.title}` });
      m.contentEl.createEl("p", { text: `後項：${e.type} ${e.title}` });
      new Setting(m.contentEl).setName("類型").addDropdown((d) => d
        .addOptions({ FS: "前項完成 → 後項開始（FS）", SS: "前項開始 → 後項開始（SS）", FF: "前項完成 → 後項完成（FF）", SF: "前項開始 → 後項完成（SF）" })
        .setValue("FS").onChange((x) => (v.type = x)));
      new Setting(m.contentEl).setName("前置天數").setDesc("工作天；負數＝重疊").addText((t) => {
        t.inputEl.type = "number";
        t.setValue("0").onChange((x) => (v.lag = parseInt(x, 10) || 0));
      });
      if (!p.id) new Setting(m.contentEl).setName("前項代號").setDesc("前項還沒有代號，給一個（不可含空白、逗號、#、~）").addText((t) => {
        t.setPlaceholder("例：ap判準").onChange((x) => (v.id = x.trim()));
        setTimeout(() => t.inputEl.focus(), 0);
      });
      new Setting(m.contentEl)
        .addButton((b) => b.setButtonText("接上").setCta().onClick(() => {
          if (!p.id && !/^[^\s,#~]+$/.test(v.id)) { new Notice("代號不可空白、不可含空白／逗號／#／~"); return; }
          res = v; m.close();
        }))
        .addButton((b) => b.setButtonText("取消").onClick(() => m.close()));
      m.onClose = () => ok(res);
      m.open();
    });
  }

  async unlinkAsk(p, e, code) {
    if (!this.linking || this.busy) return;
    if (!(await this.plugin.confirm("拆接", [`${p.title} → ${e.title}`, `拿掉後項的 接:${code}；兩邊日期都不動。`]))) return;
    await this.write(["unlink", e.match, code], `拆接：${p.title} → ${e.title}`);
  }

  /* 新增事項：組成一行 agenda 格式給 agenda.py add（格式由它驗）；有工期時日期＝開始日、行首寫完成日 */
  addEvent(tag) {
    if (this.busy) return;
    const types = [...new Set(["待辦", "提醒", "交件", "會議", "稽核", ...this.data.events.map((x) => x.type)])];
    const v = { date: iso(todayN()), type: "待辦", title: "", dur: "", id: "", tags: tag || "" };
    const m = new Modal(this.app);
    m.titleEl.setText("新增事項");
    let preview;
    const line = () => {
      const t = v.title.trim(), n = parseInt(v.dur, 10) || 0;
      if (!t || !/^\d{4}-\d{2}-\d{2}$/.test(v.date)) return null;
      const d = n > 0 ? iso(this.addWork(day(v.date), n - 1)) : v.date;
      const tags = v.tags.split(/[\s,，]+/).filter(Boolean).map((x) => " #" + x.replace(/^#/, "")).join("");
      return `${d} ${v.type} ${t}${n > 0 ? ` 工期${n}天` : ""}${v.id ? ` 代號:${v.id}` : ""}${tags}`;
    };
    const upd = () => preview.setText(line() || "（標題必填）");
    const field = (name, desc, k, type) => new Setting(m.contentEl).setName(name).setDesc(desc).addText((t) => {
      if (type) t.inputEl.type = type;
      t.setValue(v[k]).onChange((x) => { v[k] = x; upd(); });
      if (k === "title") setTimeout(() => t.inputEl.focus(), 0);
    });
    field("日期", "有工期＝開始日（行首會寫完成日）", "date", "date");
    new Setting(m.contentEl).setName("類型").setDesc("交件／稽核／會議是硬期限，引擎不推").addDropdown((d) => {
      for (const t of types) d.addOption(t, t);
      d.setValue(v.type).onChange((x) => { v.type = x; upd(); });
    });
    field("標題", "", "title");
    field("工期", "工作天，留空＝里程碑", "dur", "number");
    field("代號", "選填；要給別人接才需要", "id");
    field("tag", "第一個 tag 決定分段；空白隔開", "tags");
    m.contentEl.createEl("div", { cls: "ag-preview-h", text: "會寫入：" });
    preview = m.contentEl.createEl("code", { cls: "ag-preview" });
    upd();
    new Setting(m.contentEl)
      .addButton((b) => b.setButtonText("新增").setCta().onClick(async () => {
        const s = line();
        if (!s) { new Notice("標題必填"); return; }
        if (/[#→]/.test(v.title) || (v.id && !/^[^\s,#~]+$/.test(v.id))) { new Notice("標題不可含 # 或 →；代號不可含空白／逗號／#／~"); return; }
        m.close();
        await this.write(["add", s], `新增：${v.title.trim()}`);
      }))
      .addButton((b) => b.setButtonText("取消").onClick(() => m.close()));
    m.open();
  }

  async write(args, label) {
    this.busy = true;
    this.contentEl.addClass("ag-busy");
    try { await this.plugin.run([...args, "--source", "Obsidian 甘特圖"]); new Notice(label); } // 操作本身記進 changes.md
    catch (err) { new Notice("寫回失敗：" + err.message, 10000); }
    this.busy = false;
    this.contentEl.removeClass("ag-busy");
    await this.reload();
  }

  /* 每件事畫在哪：開始／完成（plan 有就用引擎算的 es／ef；已完成用實際完成日），回傳 null＝不在窗口 */
  span(e, w0, w1, t0) {
    if (e.rule) { if (!e.next) return null; const n = day(e.next); return n < w0 || n > w1 ? null : { s: n, f: n, ms: true }; }
    const p = e.plan;
    let s, f;
    if (p) { s = day(p.es); f = day(p.ef); }
    else {
      f = day(e.done && e.fin ? e.fin : e.date);
      s = f - (day(e.date) - day(e.start));
    }
    const ms = !e.dur && !(p && p.summary);
    let slip = null; // 硬期限延誤：條畫到寫的日期，預計完成日用虛線接出去
    if (p && p.late && !p.summary) { slip = f; f = day(e.date); }
    const overdue = !e.done && f < t0;
    if (f < w0 && !overdue) return null;
    if (s > w1) return null;
    return { s, f, ms, overdue, slip };
  }

  bar(svg, r, y, X, w0, w1, t0, where) {
    const e = r.e, sp = r.sp, p = e.plan || {};
    const g = el("g", { class: "ag-ev" }, svg);
    el("title", {}, g).textContent = e.match;
    g.addEventListener("click", () => {
      if (this.linking) this.pick(e);
      else if (!this.dragged) this.plugin.reveal(this.data.source, e.line);
    });
    if (!e.done && !e.rule && !p.summary && sp.f >= w0) this.draggable(g, e);
    const cls = [e.done ? "ag-done" : sp.overdue ? "ag-late" : "", p.critical ? "ag-crit" : "", e.rule ? "ag-rule" : ""].join(" ");
    const cs = Math.max(sp.s, w0), cf = Math.min(sp.f, w1);
    const x0 = X(cs), x1 = X(cf) + DW, cy = y + RH / 2;

    if (sp.f < w0) { // 逾期且早於窗口：貼左邊標日期
      el("text", { x: 2, y: cy + 4, class: "ag-note ag-late-t" }, g).textContent = `◀ ${md(sp.f)} 逾 ${t0 - sp.f} 天`;
      return;
    }
    // 原定（baseline）：畫在條形群組外，拖拉時固定不動；改回原定那天就不畫
    if (e.base && !e.done && e.base !== e.date) {
      const bf = day(e.base), bs = bf - (sp.f - sp.s);
      if (bf >= w0 && bs <= w1) {
        const b = sp.ms // 里程碑＝空心灰菱形；有工期＝條下細灰線
          ? el("path", { d: `M${X(bf) + DW / 2},${cy - 6} l6,6 l-6,6 l-6,-6 Z`, class: "ag-base-ms" })
          : el("line", { x1: X(Math.max(bs, w0)), x2: X(Math.min(bf, w1)) + DW, y1: y + RH - 3, y2: y + RH - 3, class: "ag-base" });
        el("title", {}, b).textContent = `原定 ${md(bf)}`;
        svg.insertBefore(b, g);
      }
    }
    if (p.summary) {
      el("path", { d: `M${x0},${y + 6} H${x1} V${y + 15} L${x1 - 5},${y + 10} H${x0 + 5} L${x0},${y + 15} Z`, class: "ag-sum " + cls }, g);
    } else if (sp.ms) {
      const mx = X(sp.f) + DW / 2;
      el("path", { d: `M${mx},${cy - 7} L${mx + 7},${cy} L${mx},${cy + 7} L${mx - 7},${cy} Z`, class: "ag-ms " + cls + (e.hard ? " ag-hard" : "") }, g);
    } else {
      const barEl = el("rect", { x: x0 + 1, y: y + 5, width: Math.max(2, x1 - x0 - 2), height: RH - 10, rx: 3, class: "ag-bar " + cls }, g);
      if (e.pct && !e.done)
        el("rect", { x: x0 + 1, y: y + 5, width: Math.max(0, (x1 - x0 - 2) * e.pct / 100), height: RH - 10, rx: 3, class: "ag-pct" }, g);
      if (e.dur && !e.done && !e.rule && !sp.slip && sp.f <= w1) this.resizable(g, barEl, e, sp, x1, y);
    }
    // 硬期限：寫的日期紅 ◆（後推時引擎 ef 已含延誤）＋晚 N 天
    if (e.hard && !e.done && !sp.ms) {
      const hd = day(e.date);
      if (hd >= w0 && hd <= w1) { const hx = X(hd) + DW / 2; el("path", { d: `M${hx},${cy - 7} L${hx + 7},${cy} L${hx},${cy + 7} L${hx - 7},${cy} Z`, class: "ag-ms ag-hard" }, g); }
    }
    if (sp.slip) {
      const a = X(sp.f) + DW / 2, b = X(Math.min(sp.slip, w1)) + DW / 2;
      el("line", { x1: a, x2: b, y1: cy, y2: cy, class: "ag-slip" }, g);
      el("circle", { cx: b, cy, r: 3, class: "ag-slip-end" }, g);
    }
    let note = e.done ? `✓ ${md(sp.f)}` : "";
    if (sp.slip) note += `預計 ${md(sp.slip)}`;
    if (p.late) note += ` 晚 ${p.late} 天`;
    // 截止：▼，超過變紅
    if (e.deadline && !e.done) {
      const dn = day(e.deadline);
      if (dn >= w0 && dn <= w1) {
        const dx = X(dn) + DW / 2;
        el("path", { d: `M${dx - 5},${y + 1} H${dx + 5} L${dx},${y + 8} Z`, class: "ag-dl" + (p.dl_late ? " ag-dl-late" : "") }, g);
      }
      const late = p.dl_late || (!e.plan && sp.f > dn ? sp.f - dn : 0);
      if (late) note += ` 超過截止 ${late} 天`;
    }
    if (e.pct && !e.done) note += ` ${e.pct}%`;
    if (sp.overdue) note += ` 逾 ${t0 - sp.f} 天`;
    if (note) el("text", { x: Math.max(sp.ms ? X(sp.f) + DW : x1, sp.slip ? X(Math.min(sp.slip, w1)) + DW : 0) + 4, y: cy + 4, class: "ag-note" + (p.late || sp.overdue ? " ag-late-t" : "") }, g).textContent = note.trim();
    if (e.id) where.set(e.id, { x0: sp.ms ? X(sp.f) + DW / 2 : x0, x1: sp.ms ? X(sp.f) + DW / 2 : x1, y, e });
    if (this.linkFrom && this.linkFrom.match === e.match) g.classList.add("ag-picked");
  }

  /* 依 sections 分組；子項（屬）跟在母項後面縮排 */
  layout(d, w0, w1, t0) {
    const secs = [...d.sections];
    if (d.events.some((e) => !e.section)) secs.unshift(null);
    const rows = [];
    for (const name of secs) {
      const evs = d.events.filter((e) => e.section === name);
      const ids = new Set(evs.filter((e) => e.id).map((e) => e.id));
      const kids = new Map();
      for (const e of evs) if (e.parent && ids.has(e.parent)) (kids.get(e.parent) || kids.set(e.parent, []).get(e.parent)).push(e);
      const out = [];
      const walk = (e, depth) => {
        const sp = this.span(e, w0, w1, t0);
        if (sp) out.push({ kind: "ev", e, sp, depth });
        for (const k of (e.id && kids.get(e.id)) || []) walk(k, depth + 1);
      };
      for (const e of evs) if (!(e.parent && ids.has(e.parent))) walk(e, 0);
      if (!out.length) continue;
      const label = name || "（未分段）", collapsed = this.plugin.collapsed().includes(label);
      rows.push({ kind: "sec", name: label, count: out.length, collapsed,
        tag: name === "例行與其他" ? null : (evs.find((e) => e.tags.length) || { tags: [null] }).tags[0] }); // 段＝第一個 tag（例行段不預填）
      if (!collapsed) rows.push(...out);
    }
    return rows;
  }
}

class Tab extends PluginSettingTab {
  constructor(app, plugin) { super(app, plugin); this.plugin = plugin; }
  display() {
    const c = this.containerEl, p = this.plugin;
    c.empty();
    c.createEl("p", { text: "設定只存在這台電腦（不進 git）。" });
    new Setting(c).setName("Python 路徑").setDesc("跑 agenda.py 用").addText((t) =>
      t.setValue(p.settings.python).onChange((v) => p.save({ python: v.trim() || "python" })));
    new Setting(c).setName("agenda.py 路徑").setDesc(`留空＝自動找（vault 的 scripts/agenda.py → 已安裝的 llm-wiki plugin）。目前用：${p.script() || "找不到"}`)
      .addText((t) => t.setPlaceholder("C:\\…\\scripts\\agenda.py").setValue(p.settings.script).onChange((v) => p.save({ script: v.trim() })));
    new Setting(c).setName("改讀別的 agenda 檔").setDesc("示範／測試用，留空＝wiki/agenda.md（agenda.py --file）").addText((t) =>
      t.setValue(p.settings.file).onChange((v) => p.save({ file: v.trim() })));
    for (const [k, n] of [["before", "今天往前幾天"], ["after", "今天往後幾天"]])
      new Setting(c).setName(n).addText((t) => t.setValue(String(p.settings[k])).onChange((v) => {
        const x = parseInt(v, 10);
        if (x >= 0 && x <= 730) p.save({ [k]: x });
      }));
  }
}

module.exports = class AgendaGantt extends Plugin {
  async onload() {
    this.key = "agenda-gantt:" + this.app.vault.getName();
    this.settings = Object.assign({}, DEFAULTS, this.local("settings") || {});
    this.registerView(VIEW, (leaf) => new GanttView(leaf, this));
    this.addRibbonIcon("gantt-chart", "開啟日程甘特圖", () => this.open());
    this.addCommand({ id: "open", name: "開啟日程甘特圖", callback: () => this.open() });
    this.addSettingTab(new Tab(this.app, this));
    let timer = null;
    this.registerEvent(this.app.vault.on("modify", (f) => {
      if (f.path !== AGENDA || this.settings.file) return;
      clearTimeout(timer);
      timer = setTimeout(() => this.views().forEach((v) => v.reload()), 1000);
    }));
  }

  local(k) { try { return JSON.parse(window.localStorage.getItem(this.key + ":" + k)); } catch (e) { return null; } }
  setLocal(k, v) { try { window.localStorage.setItem(this.key + ":" + k, JSON.stringify(v)); } catch (e) { /* 存不了就算了 */ } }
  async save(patch) { Object.assign(this.settings, patch); this.setLocal("settings", this.settings); this.views().forEach((v) => v.reload()); }
  collapsed() { return this.local("collapsed") || []; }
  async toggle(name) { const c = this.collapsed(); this.setLocal("collapsed", c.includes(name) ? c.filter((x) => x !== name) : [...c, name]); }
  views() { return this.app.workspace.getLeavesOfType(VIEW).map((l) => l.view).filter((v) => v instanceof GanttView); }

  async open() {
    const leaf = this.app.workspace.getLeavesOfType(VIEW)[0] || this.app.workspace.getLeaf("tab");
    await leaf.setViewState({ type: VIEW, active: true });
    this.app.workspace.revealLeaf(leaf);
  }

  /* agenda.py 在哪：設定值 → vault 的 scripts/agenda.py → installed_plugins.json 記的 llm-wiki 安裝目錄 */
  script() {
    const vault = this.app.vault.adapter.getBasePath(), ok = (f) => { try { return fs.statSync(f).isFile(); } catch (e) { return false; } };
    if (this.settings.script) return ok(this.settings.script) ? this.settings.script : null;
    const local = path.join(vault, "scripts", "agenda.py");
    if (ok(local)) return local;
    try {
      const reg = JSON.parse(fs.readFileSync(path.join(os.homedir(), ".claude", "plugins", "installed_plugins.json"), "utf8"));
      for (const x of (reg.plugins || reg)["llm-wiki@llm-wiki"] || []) {
        const f = path.join(x.installPath, "scripts", "agenda.py");
        if (ok(f)) return f;
      }
    } catch (e) { /* 沒裝 plugin */ }
    return null;
  }

  run(args) {
    const script = this.script();
    if (!script) return Promise.reject(new Error("找不到 agenda.py：到外掛設定填「agenda.py 路徑」"));
    args = [script, ...args];
    if (this.settings.file) args.push("--file", this.settings.file);
    const cwd = this.app.vault.adapter.getBasePath();
    const env = Object.assign({}, process.env, { PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1", CLAUDE_PROJECT_DIR: cwd });
    return new Promise((ok, bad) => execFile(this.settings.python, args, { cwd, env, windowsHide: true, maxBuffer: 32 << 20 },
      (err, out, errOut) => err ? bad(new Error((errOut || "").trim().split("\n").pop() || err.message)) : ok(out)));
  }

  async fetch() {
    const out = await this.run(["--json"]);
    try { return JSON.parse(out); } catch (e) { throw new Error("JSON 解析失敗：" + e.message); }
  }

  /* 確認框；hard＝硬期限，要再按一次才算數 */
  confirm(title, lines, hard) {
    return new Promise((ok) => {
      const m = new Modal(this.app);
      let yes = false, armed = !hard;
      m.titleEl.setText(title);
      for (const l of lines) m.contentEl.createEl("p", { text: l });
      new Setting(m.contentEl)
        .addButton((b) => b.setButtonText(hard ? "我確定要改硬期限" : "確定").setCta().onClick(() => {
          if (!armed) { armed = true; b.setButtonText("再按一次確認"); b.buttonEl.addClass("mod-warning"); return; }
          yes = true; m.close();
        }))
        .addButton((b) => b.setButtonText("取消").onClick(() => m.close()));
      m.onClose = () => ok(yes);
      m.open();
    });
  }

  async reveal(source, line) {
    const f = this.app.vault.getAbstractFileByPath(source);
    if (!f) { new Notice(`${source} 不在 vault 內，無法開啟（第 ${line} 行）`); return; }
    const leaf = this.app.workspace.getLeaf("tab");
    await leaf.openFile(f, { eState: { line: line - 1 } });
    const ed = leaf.view && leaf.view.editor;
    if (ed) { ed.setCursor({ line: line - 1, ch: 0 }); ed.scrollIntoView({ from: { line: line - 1, ch: 0 }, to: { line: line - 1, ch: 0 } }, true); }
  }
};
