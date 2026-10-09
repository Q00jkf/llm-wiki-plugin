#!/usr/bin/env python3
"""role_cards —— 角色卡（wiki/meta/roles/<角色>.md）的列表、交接成本估算、登記持有者、建卡。

為什麼：session 關掉或 /clear 後沒有記憶、ListAgents 名稱也會變；角色卡讓新 session 照卡接手，
主管從卡上的 agent 欄對到現在的 ListAgents 名稱，不必逐一發訊確認。流程見 plugin `wiki-collabteam` skill 的 role.md。

用法：
    python role_cards.py list                 # 所有角色：持有者（ListAgents 名稱）、接手時間、職稱、必讀份數、進行中行數
    python role_cards.py check [--quiet]      # 指標會不會老化：卡裡的 [[連結]]（檔案＋#標題）、必讀、疑似抄 _README 的行
    python role_cards.py cost <角色>          # 接手要讀的檔（卡＋必讀）與估計 token
    python role_cards.py claim <角色> <agent> # 接手：把 agent 與 taken 寫進卡的 frontmatter
    python role_cards.py new <角色>           # 從 Templates/角色卡模板.md 建卡（已存在就拒絕）

是否在線不歸本腳本判斷（要 ListAgents，只有 Claude session 能查）。0 token、不打網路。
"""
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib.vaultpaths import find_vault_root  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROLES_REL = Path("wiki/meta/roles")
TEMPLATE = "角色卡模板.md"
MAX_MUST_READ = 5
FM_KEYS = ("role", "agent", "taken", "office_name", "office_title", "office_team")


def split_frontmatter(text: str):
    """回傳 (欄位 dict, frontmatter 原文行列表, 正文)。沒有 frontmatter 時欄位為空。"""
    if not text.startswith("---"):
        return {}, [], text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, [], text
    lines = text[3:end].strip("\n").split("\n")
    fields = {}
    for ln in lines:
        m = re.match(r"^([A-Za-z_]+):\s*(.*)$", ln)
        if m:
            v = m.group(2).strip()
            fields[m.group(1)] = "" if v.startswith("<") else v  # 範本佔位符（<…>）＝還沒填
    return fields, lines, text[end + 4:].lstrip("\n")


WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#([^\]|]+))?(?:\|[^\]]*)?\]\]")


def strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def must_reads(body: str):
    """「必讀」那一項底下縮排的 [[連結]] 或 `路徑`，到下一個頂層 bullet 或標題為止；回傳檔案路徑（不含 #標題）。"""
    out, inside = [], False
    for ln in strip_comments(body).split("\n"):
        if re.match(r"^- .*必讀", ln):
            inside = True
            continue
        if inside and (re.match(r"^(- |#)", ln)):
            break
        if inside:
            m = WIKILINK.search(ln)
            b = re.search(r"`([^`<>]+)`", ln)
            if m and "<" not in m.group(1):
                out.append(m.group(1).strip())
            elif b:
                out.append(b.group(1).strip())
    return out


def section(body: str, title: str) -> str:
    m = re.search(rf"^## {title}\s*\n(.*?)(?=^## |\Z)", strip_comments(body), re.S | re.M)
    return m.group(1) if m else ""


def in_progress_lines(body: str) -> int:
    return sum(1 for ln in section(body, "進行中事項").split("\n") if re.match(r"^\s*- \S", ln))


def resolve(root: Path, target: str):
    """Obsidian 連結目標 → 檔案。先照路徑（可省略 .md），找不到再用檔名在 vault 內找唯一一份（Obsidian 的最短路徑寫法）。"""
    t = target.strip()
    for cand in (root / t, root / f"{t}.md"):
        if cand.is_file():
            return cand
    name = Path(t).name
    hits = [p for p in root.rglob(f"{name}.md") if ".obsidian" not in p.parts] + [p for p in root.rglob(name) if p.is_file() and ".obsidian" not in p.parts]
    hits = list(dict.fromkeys(hits))
    return hits[0] if len(hits) == 1 else None


def has_heading(path: Path, heading: str) -> bool:
    want = heading.strip()
    for ln in path.read_text(encoding="utf-8", errors="replace").split("\n"):
        m = re.match(r"^#{1,6}\s+(.*?)\s*$", ln)
        if m and m.group(1) == want:
            return True
    return False


def link_problems(root: Path, body: str):
    """卡裡每個 [[連結]]：檔案找不到或 #標題不存在就回報。範本佔位符（含 <…>）略過。"""
    out = []
    for m in WIKILINK.finditer(strip_comments(body)):
        target, heading = m.group(1), m.group(2)
        if "<" in target:
            continue
        f = resolve(root, target)
        if f is None:
            out.append(f"[[{target}]] 找不到檔案")
        elif heading and not has_heading(f, heading):
            out.append(f"[[{target}#{heading}]] 標題不存在")
    return out


def copied_lines(body: str):
    """進行中事項裡沒有指向出處（[[連結]] 或 `路徑`）又超過 40 字的行：多半是把 _README 的內容抄過來了。"""
    out = []
    for ln in section(body, "進行中事項").split("\n"):
        s = ln.strip()
        if s.startswith("- ") and len(s) > 42 and not WIKILINK.search(s) and "`" not in s:
            out.append(s[:30] + "…")
    return out


def est_tokens(text: str) -> int:
    """粗估：中日韓字約 1 token／字，其餘約 4 bytes／token。只拿來比大小，不是精確值。"""
    cjk = sum(1 for ch in text if "　" <= ch <= "鿿" or "＀" <= ch <= "￯")
    rest = len(text.encode("utf-8")) - cjk * 3
    return cjk + max(0, rest) // 4


def card_path(root: Path, role: str) -> Path:
    return root / ROLES_REL / f"{role}.md"


def load(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    fields, _, body = split_frontmatter(text)
    return text, fields, body


def all_cards(root: Path):
    d = root / ROLES_REL
    return sorted(p for p in d.glob("*.md") if not p.name.startswith("_")) if d.is_dir() else []


def card_problems(root: Path, body: str):
    reads = must_reads(body)
    out = []
    if len(reads) > MAX_MUST_READ:
        out.append(f"必讀 {len(reads)} 份 > {MAX_MUST_READ}")
    out += [f"必讀找不到：{r}" for r in reads if resolve(root, r) is None and not Path(r).exists()]
    out += [p for p in link_problems(root, body) if not any(p.startswith(f"[[{r}]]") for r in reads)]
    out += [f"疑似抄了 _README（沒有指向出處）：{c}" for c in copied_lines(body)]
    return out


def cmd_list(root: Path) -> int:
    cards = all_cards(root)
    if not cards:
        print(f"沒有角色卡（{ROLES_REL.as_posix()}/ 不存在或是空的）。建卡：python role_cards.py new <角色>")
        return 0
    print("| 角色 | 持有者（ListAgents） | 接手 | 職稱 | 必讀 | 進行中 | 注意 |")
    print("|---|---|---|---|---|---|---|")
    for p in cards:
        _, f, body = load(p)
        reads = must_reads(body)
        n = len(card_problems(root, body))
        print(f"| {f.get('role') or p.stem} | {f.get('agent') or '（無人）'} | {f.get('taken') or '—'} | {f.get('office_title') or '—'} | {len(reads)} | {in_progress_lines(body)} | {f'{n} 項，跑 check' if n else ''} |")
    return 0


def cmd_check(root: Path, quiet: bool) -> int:
    """每張卡的連結（檔案＋標題）、必讀清單、疑似抄 README 的行。斷掉的只回報，不自動修 —— 猜錯位置比斷掉更糟。"""
    total = 0
    for p in all_cards(root):
        _, _, body = load(p)
        probs = card_problems(root, body)
        total += len(probs)
        if probs:
            print(f"🔴 {p.relative_to(root).as_posix()}")
            for x in probs:
                print(f"   - {x}")
        elif not quiet:
            print(f"✅ {p.relative_to(root).as_posix()}")
    if total == 0 and not quiet:
        print("角色卡沒有斷掉的指標")
    return 0


def cmd_cost(root: Path, role: str) -> int:
    p = card_path(root, role)
    if not p.is_file():
        print(f"沒有這張角色卡：{p.relative_to(root).as_posix()}")
        return 1
    text, _, body = load(p)
    rows = [(p.relative_to(root).as_posix(), est_tokens(text), True)]
    for r in must_reads(body):
        f = Path(r) if Path(r).is_absolute() else resolve(root, r)
        if f is not None and f.is_file():
            rows.append((r, est_tokens(f.read_text(encoding="utf-8", errors="replace")), True))
        else:
            rows.append((r, 0, False))
    print("| 檔 | 估計 token |")
    print("|---|---|")
    for name, tok, ok in rows:
        print(f"| `{name}` | {tok if ok else '找不到'} |")
    total = sum(t for _, t, _ in rows)
    print(f"\n合計約 {total} token（粗估；不含守門腳本的輸出）")
    if len(rows) - 1 > MAX_MUST_READ:
        print(f"⚠️ 必讀 {len(rows) - 1} 份，超過上限 {MAX_MUST_READ}：請使用者或主管精簡")
    return 0


def cmd_claim(root: Path, role: str, agent: str) -> int:
    p = card_path(root, role)
    if not p.is_file():
        print(f"沒有這張角色卡：{p.relative_to(root).as_posix()}")
        return 1
    text = p.read_text(encoding="utf-8", errors="replace")
    fields, lines, body = split_frontmatter(text)
    if not lines:
        print("角色卡沒有 frontmatter，無法登記；請照 Templates/角色卡模板.md 補上")
        return 1
    prev = fields.get("agent", "")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_lines, seen = [], set()
    for ln in lines:
        m = re.match(r"^([A-Za-z_]+):", ln)
        key = m.group(1) if m else None
        if key == "agent":
            ln = f"agent: {agent}"
        elif key == "taken":
            ln = f"taken: {now}"
        if key:
            seen.add(key)
        new_lines.append(ln)
    if "agent" not in seen:
        new_lines.append(f"agent: {agent}")
    if "taken" not in seen:
        new_lines.append(f"taken: {now}")
    p.write_text("---\n" + "\n".join(new_lines) + "\n---\n" + body, encoding="utf-8")
    print(f"已登記：{role} ← {agent}（{now}）" + (f"；前一位持有者 {prev}" if prev and prev != agent else ""))
    return 0


def cmd_new(root: Path, role: str) -> int:
    p = card_path(root, role)
    if p.exists():
        print(f"已經有這張卡：{p.relative_to(root).as_posix()}")
        return 1
    candidates = [root / "Templates" / TEMPLATE, Path(__file__).resolve().parent.parent / "templates" / "vault" / "Templates" / TEMPLATE]
    tpl = next((c for c in candidates if c.is_file()), None)
    if tpl is None:
        print(f"找不到範本 {TEMPLATE}")
        return 1
    text = tpl.read_text(encoding="utf-8").replace("<角色名>", role, 1)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    print(f"已建卡：{p.relative_to(root).as_posix()}（請填「定義」段：職責、必讀、守門腳本）")
    return 0


def main(argv) -> int:
    root = find_vault_root(Path.cwd())
    if root is None:
        print("不在 vault 裡（找不到 wiki/ 或 raw/.manifest.json）")
        return 1
    if not argv or argv[0] == "list":
        return cmd_list(root)
    cmd, args = argv[0], argv[1:]
    if cmd == "check":
        return cmd_check(root, "--quiet" in args)
    if cmd == "cost" and len(args) == 1:
        return cmd_cost(root, args[0])
    if cmd == "claim" and len(args) == 2:
        return cmd_claim(root, args[0], args[1])
    if cmd == "new" and len(args) == 1:
        return cmd_new(root, args[0])
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
