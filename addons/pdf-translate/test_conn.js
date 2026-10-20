// pdf-translate 連線設定（local-config.json）的測試：從 main.js 擷取 DIRECT～headers() 單獨跑，不載入 Obsidian。
// 用法：node addons/pdf-translate/test_conn.js
const fs = require("fs"), nodePath = require("path"), os = require("os"), assert = require("assert");
const src = fs.readFileSync(process.argv[2] || nodePath.join(__dirname, "obsidian", "main.js"), "utf8");
const start = src.indexOf("const DIRECT = ");
const end = src.indexOf("\n}\n", src.indexOf("function headers()")) + 3;
const execFileSync = () => { throw new Error("no reg"); }; // 只測環境變數路徑
const mk = new Function("fs", "nodePath", "execFileSync", "process",
  src.slice(start, end) + "\nreturn { CONN, loadConn, headers };");

const DIRECT = "https://api.anthropic.com/v1/messages";
const ENV = { ANTHROPIC_API_KEY: "REAL-KEY", GITHUB_TOKEN: "gh", NAS_PROXY_TOKEN: "t1" };
let n = 0;
function run(cfg, env = ENV) {
  const dir = fs.mkdtempSync(nodePath.join(os.tmpdir(), "pt-"));
  if (cfg !== undefined) fs.writeFileSync(nodePath.join(dir, "local-config.json"), typeof cfg === "string" ? cfg : JSON.stringify(cfg));
  const m = mk(fs, nodePath, execFileSync, { env });
  m.loadConn(dir);
  return m;
}
function direct(m, why) {  // 設定被拒：維持直連、有警告、送的是本來的金鑰（不是送去別處）
  assert.strictEqual(m.CONN.endpoint, DIRECT, why);
  assert.strictEqual(m.CONN.custom, false, why);
  assert.ok(m.CONN.warning, why + "：應有側欄警告");
  n++;
}
function t(name, fn) { fn(); n++; }

t("沒設定檔 → 直連、讀 ANTHROPIC_API_KEY、無警告", () => {
  const m = run(undefined);
  assert.strictEqual(m.CONN.endpoint, DIRECT);
  assert.strictEqual(m.headers()["x-api-key"], "REAL-KEY");
  assert.strictEqual(m.CONN.warning, "");
});
t("內網 http＋合法 keyEnv → 走轉發、送通行碼", () => {
  const m = run({ endpoint: "http://192.168.10.5:4000/v1/messages", keyEnv: "NAS_PROXY_TOKEN" });
  assert.strictEqual(m.CONN.endpoint, "http://192.168.10.5:4000/v1/messages");
  assert.strictEqual(m.headers()["x-api-key"], "t1");
});
t("外網 https＋合法 keyEnv → 走轉發", () => {
  const m = run({ endpoint: "https://proxy.example.com/v1/messages", keyEnv: "NAS_PROXY_TOKEN" });
  assert.strictEqual(m.headers()["x-api-key"], "t1");
});
t("轉發設定但這台沒通行碼 → 錯誤講通行碼", () => {
  const m = run({ endpoint: "http://nas.local:4000/v1/messages", keyEnv: "NAS_PROXY_TOKEN" }, {});
  assert.throws(() => m.headers(), /NAS_PROXY_TOKEN.*通行碼/);
});
// 🔴 主管審 1.11.0：改一行 endpoint 不可把真金鑰送出去
direct(run({ endpoint: "https://evil.example.com/v1/messages" }), "自訂 endpoint 沒 keyEnv");
direct(run({ endpoint: "https://evil.example.com/v1/messages", keyEnv: "ANTHROPIC_API_KEY" }), "keyEnv 指向真金鑰");
direct(run({ endpoint: "https://evil.example.com/v1/messages", keyEnv: "GITHUB_TOKEN" }), "keyEnv 指向其他密碼");
direct(run({ endpoint: "http://evil.example.com/v1/messages", keyEnv: "NAS_PROXY_TOKEN" }), "外網 http");
direct(run({ endpoint: "http://172.32.0.1/v1/messages", keyEnv: "NAS_PROXY_TOKEN" }), "172.32 不是私有網段");
direct(run({ endpoint: "file:///etc/passwd", keyEnv: "NAS_PROXY_TOKEN" }), "非 http(s)");
direct(run({ keyEnv: "NAS_PROXY_TOKEN" }), "缺 endpoint");
direct(run("{oops"), "壞 JSON");
t("被拒時送出的是直連＋本來的金鑰（不是轉給別處）", () => {
  const m = run({ endpoint: "https://evil.example.com/v1/messages" });
  assert.strictEqual(m.CONN.endpoint, DIRECT);
  assert.strictEqual(m.headers()["x-api-key"], "REAL-KEY");
});
t("私有位址判斷", () => {
  for (const h of ["http://localhost:4000/x", "http://127.0.0.1/x", "http://10.1.2.3/x", "http://172.16.0.1/x", "http://172.31.255.1/x", "http://nas.local/x", "http://[::1]:4000/x"]) {
    const m = run({ endpoint: h, keyEnv: "NAS_PROXY_TOKEN" });
    assert.strictEqual(m.CONN.custom, true, h);
  }
});
console.log(`${n}/${n} OK`);
