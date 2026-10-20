// pdf-translate 連線設定（local-config.json）的測試：從 main.js 擷取 CONN／loadConn／apiKey／headers 單獨跑。用法：node addons/pdf-translate/test_conn.js
const fs = require("fs"), nodePath = require("path"), os = require("os"), assert = require("assert");
const src = fs.readFileSync(process.argv[2] || nodePath.join(__dirname, "obsidian", "main.js"), "utf8");
const start = src.indexOf("const CONN = ");
const end = src.indexOf("\n}\n", src.indexOf("function headers()")) + 3;
const execFileSync = () => { throw new Error("no reg"); }; // 只測環境變數路徑
const mk = new Function("fs", "nodePath", "execFileSync", "process",
  src.slice(start, end) + "\nreturn { CONN, loadConn, headers };");

function run(cfg, env) {
  const dir = fs.mkdtempSync(nodePath.join(os.tmpdir(), "pt-"));
  if (cfg !== undefined) fs.writeFileSync(nodePath.join(dir, "local-config.json"), typeof cfg === "string" ? cfg : JSON.stringify(cfg));
  const m = mk(fs, nodePath, execFileSync, { env });
  m.loadConn(dir);
  return m;
}

// 1. 沒設定檔 → 直連、讀 ANTHROPIC_API_KEY
let m = run(undefined, { ANTHROPIC_API_KEY: "k1" });
assert.strictEqual(m.CONN.endpoint, "https://api.anthropic.com/v1/messages");
assert.strictEqual(m.headers()["x-api-key"], "k1");
// 2. 轉發設定 → 換網址、讀指定變數，不讀 ANTHROPIC_API_KEY
m = run({ endpoint: "http://nas.local:4000/v1/messages", keyEnv: "PROXY_TOKEN" }, { ANTHROPIC_API_KEY: "real", PROXY_TOKEN: "t1" });
assert.strictEqual(m.CONN.endpoint, "http://nas.local:4000/v1/messages");
assert.strictEqual(m.headers()["x-api-key"], "t1");
// 3. 轉發設定但沒通行碼 → 錯誤訊息講通行碼
m = run({ endpoint: "http://nas.local:4000/v1/messages", keyEnv: "PROXY_TOKEN" }, {});
assert.throws(() => m.headers(), /PROXY_TOKEN.*通行碼/);
// 4. 非法值被忽略（不是 URL、變數名含特殊字元）
m = run({ endpoint: "file:///etc/passwd", keyEnv: "A;rm -rf" }, { ANTHROPIC_API_KEY: "k1" });
assert.strictEqual(m.CONN.endpoint, "https://api.anthropic.com/v1/messages");
assert.strictEqual(m.CONN.keyEnv, "ANTHROPIC_API_KEY");
// 5. 壞 JSON → 維持預設
m = run("{oops", { ANTHROPIC_API_KEY: "k1" });
assert.strictEqual(m.CONN.custom, false);
console.log("5/5 OK");
