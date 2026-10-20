/* 工具箱（toolbox）—— 2026-10-17
 * 清單不手寫：掃 vault 內每個 <入口檔>.tool.json（放在工具旁），依 category 分組。
 * 直接用 JS 讀說明檔，同事沒裝 Python 也能看清單（使用者 10-17）；檢查規則照 scripts/toolbox.py check_one，改規則兩邊一起改。
 * html＝系統預設瀏覽器開；python＝先 toolbox.py --deps 查套件，第一次執行先確認，cwd＝工具資料夾；
 * exe 有 download（太大不進 git）＝開下載連結，在 vault 內＝直接執行。設定存本機 localStorage，不寫 data.json（免得進 git）。
 * obsidian＝vault 裡的 Obsidian 外掛（entry＝外掛 id），按下去執行 command，沒寫就開它的設定頁（主管 10-19 轉使用者需求）。
 * external＝工具在 vault 外（只在擁有者電腦上），這台有那個資料夾就照常開，沒有就不列（有 download 改顯示下載）（使用者 10-18「個人的不用顯示」）。
 */
const { Plugin, ItemView, Notice, Modal, Setting, PluginSettingTab } = require("obsidian");
const { execFile, spawn } = require("child_process");
const fs = require("fs"), os = require("os"), nodePath = require("path");

const VIEW = "toolbox";
const SUFFIX = ".tool.json";
const TYPES = ["html", "python", "exe", "obsidian"];
const REQUIRED = ["name", "type", "entry", "desc", "category"];
const LISTS = ["tags", "deps", "optional"], STRS = ["run", "author", "download", "version", "note", "external", "owner", "remote", "command"];
const DEFAULTS = { python: "python" };
const EARLY = 8000; // 啟動後這幾毫秒內就結束且 exit≠0 → 當成崩潰，跳錯誤
const strs = (x) => Array.isArray(x) && x.every((s) => typeof s === "string");

/* 一份說明檔 → { tool, bad }（同 toolbox.py check_one） */
async function checkOne(app, f) {
  let d;
  try { d = JSON.parse(await app.vault.cachedRead(f)); }
  catch (e) { return { tool: null, bad: [`${f.path}: 讀不到或不是 JSON（${e.message}）`] }; }
  if (!d || typeof d !== "object" || Array.isArray(d)) return { tool: null, bad: [`${f.path}: 要是 JSON 物件`] };
  let bad = REQUIRED.filter((k) => !(typeof d[k] === "string" && d[k].trim())).map((k) => `${f.path}: 缺 ${k}`);
  for (const k of LISTS) if (k in d && !strs(d[k])) bad.push(`${f.path}: ${k} 要是字串陣列`);
  for (const k of STRS) if (k in d && typeof d[k] !== "string") bad.push(`${f.path}: ${k} 要是字串`);
  if (bad.length) return { tool: null, bad };
  const ext = (d.external || "").trim(), dl = (d.download || "").trim(), plug = d.type === "obsidian";
  const dir = f.parent && f.parent.path !== "/" ? f.parent.path + "/" : "", path = ext ? nodePath.join(ext, d.entry).replace(/\\/g, "/") : plug ? `.obsidian/plugins/${d.entry}` : dir + d.entry;
  if (ext && !nodePath.isAbsolute(ext)) bad.push(`${f.path}: external 要是絕對路徑`);
  if (ext) for (const k of ["owner", "remote"]) if (!(d[k] || "").trim()) bad.push(`${f.path}: 有 external 要寫 ${k}`);
  const here = ext ? nodePath.isAbsolute(ext) && fs.existsSync(path) : plug ? !!app.plugins.manifests[d.entry] : !!app.vault.getAbstractFileByPath(path);
  if (plug && !here) bad.push(`${f.path}: 外掛 ${d.entry} 沒裝（.obsidian/plugins/${d.entry}/manifest.json 不存在）`);
  if (!TYPES.includes(d.type)) bad.push(`${f.path}: type 只能是 ${TYPES.join("／")}（寫了 ${d.type}）`);
  if (f.name !== d.entry + SUFFIX) bad.push(`${f.path}: 檔名要是 ${d.entry}${SUFFIX}（說明檔放在工具旁邊）`);
  if (dl && !dl.startsWith("https://")) bad.push(`${f.path}: download 要是 https:// 連結`);
  else if (!dl && !ext && !here) bad.push(`${f.path}: 入口檔 ${d.entry} 不存在（不進 git 的檔案要寫 download）`);
  if (d.type === "html" && !/\.html?$/i.test(d.entry)) bad.push(`${f.path}: type html 的入口檔要是 .html`);
  if ((d.type === "python" || (d.type === "exe" && !dl)) && !(d.run || "").trim()) bad.push(`${f.path}: type ${d.type} 要寫 run（執行指令）`);
  if (bad.length) return { tool: null, bad };
  const t = { ...d, spec: f.path, path, here, dir: ext || dir.replace(/\/$/, "") };
  for (const k of LISTS) t[k] = d[k] || [];
  return { tool: t, bad: [] };
}

/* 卡片的動作：開啟／執行／下載（external 不在這台＝下載；沒有 download 的已在 scan 濾掉） */
const action = (t) => (t.type === "html" || t.type === "obsidian") && t.here ? "開啟" : t.download && !t.here ? "下載" : "執行";

class ToolboxView extends ItemView {
  constructor(leaf, plugin) { super(leaf); this.plugin = plugin; this.q = ""; }
  getViewType() { return VIEW; }
  getDisplayText() { return "工具箱"; }
  getIcon() { return "wrench"; }

  async onOpen() {
    this.addAction("refresh-cw", "重新掃描", () => this.reload());
    this.contentEl.addClass("tb-view");
    await this.reload();
  }

  async reload() {
    try { this.data = await this.plugin.scan(); this.err = null; }
    catch (e) { this.err = String(e.message || e); }
    this.render();
  }

  render() {
    const c = this.contentEl;
    c.empty();
    if (this.err) {
      c.createDiv({ cls: "tb-warn", text: `工具箱讀取失敗：${this.err}` });
      c.createDiv({ cls: "tb-hint", text: "請按右上角「重新掃描」；仍失敗請回報（有 Python 的電腦可跑 python scripts/toolbox.py --check 查原因）。" });
      return;
    }
    if (!this.data) { c.createDiv({ cls: "tb-hint", text: "掃描中…" }); return; }
    const { tools, problems } = this.data;
    const top = c.createDiv({ cls: "tb-top" });
    const search = top.createEl("input", { cls: "tb-search", attr: { type: "search", placeholder: "搜尋名稱、說明、tag…" } });
    search.value = this.q;
    search.oninput = () => { this.q = search.value; this.draw(list); };
    top.createSpan({ cls: "tb-count", text: `${tools.length} 個工具` });
    if (problems.length) {
      const w = c.createEl("details", { cls: "tb-warn" });
      const n = new Set(problems.map((p) => p.split(": ")[0])).size;
      w.createEl("summary", { text: `⚠️ ${n} 份說明檔有問題（${problems.length} 項），沒列出（格式見 raw/shared/RD/tools/_README.md）` });
      for (const p of problems) w.createDiv({ text: p });
    }
    const list = c.createDiv({ cls: "tb-list" });
    if (!tools.length) {
      list.createDiv({ cls: "tb-hint", text: "還沒有工具。在工具旁放一份「<入口檔>.tool.json」就會出現在這裡（格式見 raw/shared/RD/tools/_README.md）。" });
      return;
    }
    this.draw(list);
  }

  draw(list) {
    list.empty();
    const q = this.q.trim().toLowerCase();
    const hit = this.data.tools.filter((t) => !q || [t.name, t.desc, t.category, t.path, t.note || "", ...t.tags].join(" ").toLowerCase().includes(q));
    if (!hit.length) { list.createDiv({ cls: "tb-hint", text: "沒有符合的工具" }); return; }
    let cat = null, grid;
    for (const t of hit) {
      if (t.category !== cat) {
        cat = t.category;
        list.createDiv({ cls: "tb-cat", text: cat });
        grid = list.createDiv({ cls: "tb-grid" });
      }
      this.card(grid, t);
    }
  }

  card(grid, t) {
    const card = grid.createDiv({ cls: "tb-card" });
    const h = card.createDiv({ cls: "tb-head" });
    h.createSpan({ cls: "tb-type tb-type-" + t.type, text: t.type });
    h.createSpan({ cls: "tb-name", text: t.name });
    h.createSpan({ cls: "tb-act", text: action(t) });
    card.createDiv({ cls: "tb-desc", text: t.desc });
    if (t.note) card.createDiv({ cls: "tb-note", text: t.note });
    if (t.tags.length) {
      const tg = card.createDiv({ cls: "tb-tags" });
      for (const x of t.tags) tg.createSpan({ cls: "tb-tag", text: "#" + x });
    }
    const meta = [t.download && !t.here ? t.entry : t.path, t.owner && `擁有者 ${t.owner}`, t.version && `版本 ${t.version}`, t.author && `作者 ${t.author}`,
      t.deps.length && `相依 ${t.deps.map((x) => x.split(":")[0]).join("、")}`].filter(Boolean).join("｜");
    card.createDiv({ cls: "tb-meta", text: meta });
    card.title = { 開啟: t.type === "obsidian" ? (t.command ? `執行 Obsidian 指令 ${t.command}` : "打開這個外掛的設定頁") : "用系統預設瀏覽器開啟", 下載: "用瀏覽器開下載頁（檔案太大不進 git）", 執行: `執行：${t.run}（工作資料夾＝工具所在資料夾）` }[action(t)];
    card.onclick = () => this.plugin.launch(t);
  }
}

class Tab extends PluginSettingTab {
  constructor(app, plugin) { super(app, plugin); this.plugin = plugin; }
  display() {
    const c = this.containerEl, p = this.plugin;
    c.empty();
    c.createEl("p", { text: "設定只存在這台電腦（不進 git）。" });
    new Setting(c).setName("Python 路徑").setDesc("執行 python 工具用；例：python、py、C:\\Python312\\python.exe").addText((t) =>
      t.setValue(p.settings.python).onChange((v) => p.save({ python: v.trim() || "python" })));
    new Setting(c).setName("重設「第一次執行要確認」").setDesc("清掉已確認過的工具，下次執行每支都再問一次").addButton((b) =>
      b.setButtonText("重設").onClick(() => { p.setLocal("trusted", []); new Notice("已重設"); }));
  }
}

module.exports = class Toolbox extends Plugin {
  async onload() {
    this.key = "toolbox:" + this.app.vault.getName();
    this.settings = Object.assign({}, DEFAULTS, this.local("settings") || {});
    this.registerView(VIEW, (leaf) => new ToolboxView(leaf, this));
    this.addRibbonIcon("wrench", "開啟工具箱", () => this.open());
    this.addCommand({ id: "open", name: "開啟工具箱", callback: () => this.open() });
    this.addSettingTab(new Tab(this.app, this));
    let timer = null;
    const touch = (f) => {
      if (!f || !f.path.endsWith(SUFFIX)) return;
      clearTimeout(timer);
      timer = setTimeout(() => this.views().forEach((v) => v.reload()), 500);
    };
    this.app.workspace.onLayoutReady(() => {
      for (const ev of ["create", "modify", "delete"]) this.registerEvent(this.app.vault.on(ev, touch));
      this.registerEvent(this.app.vault.on("rename", (f, old) => touch(old.endsWith(SUFFIX) ? { path: old } : f)));
    });
  }

  local(k) { try { return JSON.parse(window.localStorage.getItem(this.key + ":" + k)); } catch (e) { return null; } }
  setLocal(k, v) { try { window.localStorage.setItem(this.key + ":" + k, JSON.stringify(v)); } catch (e) { /* 存不了就算了 */ } }
  save(patch) { Object.assign(this.settings, patch); this.setLocal("settings", this.settings); }
  views() { return this.app.workspace.getLeavesOfType(VIEW).map((l) => l.view).filter((v) => v instanceof ToolboxView); }
  full(p) { return this.app.vault.adapter.getFullPath(p); }

  async open() {
    const leaf = this.app.workspace.getLeavesOfType(VIEW)[0] || this.app.workspace.getLeaf("tab");
    await leaf.setViewState({ type: VIEW, active: true });
    this.app.workspace.revealLeaf(leaf);
  }

  async scan() {
    const files = this.app.vault.getFiles().filter((f) => f.name.endsWith(SUFFIX));
    const tools = [], problems = [];
    for (const f of files) {
      const { tool, bad } = await checkOne(this.app, f);
      problems.push(...bad);
      if (tool && (tool.here || tool.download)) tools.push(tool); // 個人工具（external 不在這台、沒 download）不列
    }
    tools.sort((a, b) => (a.category < b.category ? -1 : a.category > b.category ? 1 : a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    return { tools, problems: problems.sort() };
  }

  async launch(t) {
    if (this.busy) return;
    const a = action(t), electron = require("electron");
    if (t.type === "obsidian") { // vault 裡的外掛：執行指令，沒寫 command 就開設定頁
      const app = this.app;
      if (!app.plugins.enabledPlugins.has(t.entry)) return new Notice(`${t.name}：外掛沒啟用（設定 → 第三方外掛 → ${t.entry}）`, 8000);
      if (!t.command) { app.setting.open(); return app.setting.openTabById(t.entry); }
      if (!app.commands.executeCommandById(t.command)) new Notice(`${t.name}：找不到指令 ${t.command}`, 8000);
      return;
    }
    if (a === "開啟") { // vault 相對路徑 → 這台電腦的絕對路徑 → 系統預設程式（.html＝預設瀏覽器）
      const err = await electron.shell.openPath(t.external ? t.path : this.full(t.path));
      return new Notice(err ? `開不了 ${t.name}：${err}` : `已開啟：${t.name}`, err ? 10000 : 4000);
    }
    if (a === "下載") {
      if (!(await this.confirm(`下載：${t.name}`, [`會用瀏覽器開下載頁：${t.download}`, t.note, `下載後執行 ${t.entry}（解壓縮後跟旁邊的檔案放在同一個資料夾）。`].filter(Boolean)))) return;
      return electron.shell.openExternal(t.download);
    }
    this.busy = true;
    try { await this.runTool(t); } catch (e) { new Notice(`${t.name}：${e.message}`, 12000); }
    this.busy = false;
  }

  /* python／vault 內 exe：①（python）查 Python 與套件 ② 第一次執行先確認 ③ cwd＝工具資料夾啟動，早退就報錯 */
  async runTool(t) {
    const argv = t.run.match(/"[^"]*"|\S+/g).map((x) => x.replace(/^"|"$/g, ""));
    const py = argv[0].toLowerCase() === "python";
    if (py) argv[0] = this.settings.python;
    const extra = [];
    if (t.type === "python") {
      let rep;
      try { rep = JSON.parse(await this.exec(this.settings.python, ["scripts/toolbox.py", "--deps", t.spec], this.full(""))); }
      catch (e) {
        throw new Error(/ENOENT|not recognized|找不到/.test(e.message)
          ? `這台電腦找不到 Python（「${this.settings.python}」）。請安裝 Python 3.10+，或到 設定 → 工具箱 填 Python 路徑。`
          : `檢查套件失敗：${e.message}`);
      }
      if (rep.problems) throw new Error(rep.problems.join("；"));
      if (rep.missing.length) return this.missingDialog(t, rep);
      if (rep.optional_missing.length) extra.push(`選配套件沒裝（缺了照樣能開，部分功能不能用）：${rep.optional_missing.join("、")}`);
    }
    const trusted = this.local("trusted") || [], sig = `${t.spec}|${t.run}`;
    if (!trusted.includes(sig)) {
      const lines = [`執行：${argv.join(" ")}`, `工作資料夾：${t.dir || "（vault 根目錄）"}`, ...extra,
        "第一次從工具箱執行這支工具；按「執行」後之後不再問（設定可重設）。"];
      if (!(await this.confirm(`執行：${t.name}`, lines))) return;
      this.setLocal("trusted", [...trusted, sig]);
    } else if (extra.length) new Notice(extra.join("\n"), 8000);
    const log = nodePath.join(os.tmpdir(), `toolbox-${t.entry.replace(/[^\w.-]/g, "_")}.log`);
    const fd = fs.openSync(log, "w"); // 輸出寫暫存檔：Obsidian 關掉後工具照跑，不會因為管線斷掉而當掉
    const env = Object.assign({}, process.env, { PYTHONIOENCODING: "utf-8" }); // 只改 stdio 編碼（錯誤訊息才讀得懂），不動工具讀檔的預設編碼
    // 不加 windowsHide：Windows 會把 SW_HIDE 套到程式第一個視窗，GUI 主畫面被藏起來（10-17 MPLogScope 實踩）。
    // detached＝DETACHED_PROCESS，本來就不開命令列視窗。
    const child = spawn(argv[0], argv.slice(1), { cwd: t.external || this.full(t.dir), env, detached: true, stdio: ["ignore", fd, fd] });
    fs.closeSync(fd);
    await new Promise((ok, bad) => {
      const timer = setTimeout(() => { child.unref(); new Notice(`已啟動：${t.name}`); ok(); }, EARLY);
      child.on("error", (e) => { clearTimeout(timer); bad(new Error(e.code === "ENOENT" ? `找不到「${argv[0]}」` : e.message)); });
      child.on("exit", (code) => {
        clearTimeout(timer);
        if (!code) return ok(new Notice(`${t.name} 已結束`));
        let tail = "";
        try { tail = fs.readFileSync(log, "utf8").trim().split(/\r?\n/).slice(-3).join("\n"); } catch (e) { /* 讀不到就只報 exit code */ }
        bad(new Error(`啟動失敗（exit ${code}）${tail ? "：\n" + tail : ""}\n完整輸出：${log}`));
      });
    });
  }

  missingDialog(t, rep) {
    const m = new Modal(this.app);
    m.titleEl.setText(`${t.name}：缺套件，先不執行`);
    m.contentEl.createEl("p", { text: `這台 Python ${rep.python} 缺：${rep.missing.join("、")}${rep.optional_missing.length ? `（選配另缺 ${rep.optional_missing.join("、")}）` : ""}` });
    m.contentEl.createEl("p", { text: "在終端機（PowerShell）跑下面這行安裝，裝好再按一次工具：" });
    m.contentEl.createEl("code", { cls: "tb-cmd", text: rep.pip });
    new Setting(m.contentEl)
      .addButton((b) => b.setButtonText("複製指令").setCta().onClick(() => { navigator.clipboard.writeText(rep.pip); new Notice("已複製"); }))
      .addButton((b) => b.setButtonText("關閉").onClick(() => m.close()));
    m.open();
  }

  exec(cmd, args, cwd) {
    const env = Object.assign({}, process.env, { PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" });
    return new Promise((ok, bad) => execFile(cmd, args, { cwd, env, windowsHide: true, timeout: 30000 }, (err, out, errOut) =>
      err ? bad(new Error(err.code === "ENOENT" ? "ENOENT" : (errOut || "").trim().split("\n").pop() || err.message)) : ok(out)));
  }

  confirm(title, lines) {
    return new Promise((ok) => {
      const m = new Modal(this.app);
      let yes = false;
      m.titleEl.setText(title);
      for (const l of lines) m.contentEl.createEl("p", { text: l });
      new Setting(m.contentEl)
        .addButton((b) => b.setButtonText(title.startsWith("下載") ? "開下載頁" : "執行").setCta().onClick(() => { yes = true; m.close(); }))
        .addButton((b) => b.setButtonText("取消").onClick(() => m.close()));
      m.onClose = () => ok(yes);
      m.open();
    });
  }
};
