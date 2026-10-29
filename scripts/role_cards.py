#!/usr/bin/env python3
"""role_cards —— 角色卡的列表、交接成本估算、接手、建卡、從舊位置搬遷。

位置與格式照 pixel-office skill `team`（1.16.0 起）：卡 `.claude/office/roles/<角色>.md` 只放定義，
做到哪寫 `.claude/office/checkpoints/<角色>.md`（只往後加、不進 git），誰在線由主管記在 `.claude/office/collab.md`「在線」。
還沒搬的舊 vault（`wiki/meta/roles/`、`wiki/meta/coordination.md`）照讀；`migrate` 搬過去。流程見 `wiki-collabteam` 的 role.md。

用法：
    python role_cards.py list                 # 所有角色：持有者（collab.md「在線」）、職稱、必讀份數、最後檢查點
    python role_cards.py check [--quiet]      # 指標會不會老化：卡與最後一筆檢查點的 [[連結]]（檔案＋#標題）、必讀、疑似抄 _README 的行
    python role_cards.py cost <角色>          # 接手要讀的檔（卡＋必讀＋最後一筆檢查點）與估計 token
    python role_cards.py claim <角色> <agent> # 接手：印最後一筆檢查點與辦公室登記那行（不寫卡）
    python role_cards.py new <角色>           # 從 Templates/角色卡模板.md 建卡（已存在就拒絕）
    python role_cards.py migrate [--dry-run]  # 舊 wiki/meta/roles/、coordination.md → .claude/office/

是否在線不歸本腳本判斷（要 ListAgents，只有 Claude session 能查）。0 token、不打網路。
"""
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib.vaultpaths import (CHECKPOINTS_REL, COLLAB_REL, OFFICE_REL, OLD_COORD_REL, OLD_ROLES_REL,  # noqa: E402
                             ROLES_REL, collab_path, find_vault_root, roles_dir)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TEMPLATE = "角色卡模板.md"
MAX_MUST_READ = 5
FM_KEYS = ("role", "source", "layer", "reports_to", "office_name", "office_title")


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

COORD_REL = COLLAB_REL
# 「# 主管」（team 格式）；舊 coordination.md 的「# 主管名單」「# 目前主管」照讀 —— 被 .skeleton-policy 排除，樣板改了推不到舊 vault
MANAGER_SECTION = re.compile(r"^#\s*(?:主管|主管名單|目前主管)\s*$")
ONLINE_SECTION = re.compile(r"^#\s*(?:在線|Session 狀態)\s*$")
NEXT_HEADING = re.compile(r"^#\s+")
SEPARATOR_ROW = re.compile(r"^\|?\s*:?-{2,}")


def manager_name(cell: str) -> str:
    """主管欄或舊格式那一行 → 名稱：去 **、`、[ref]，切在第一個空白或全形註記前。

    不套「至少一個連字號」的名稱正則：這台的 ListAgents 名稱常是中文（willy主管辦公室）或沒有連字號（office），
    套了會整列丟掉、再被「只有一位」退路判給別人（B 期驗收 B1，主管 office 2026-10-26 裁示）。
    """
    t = re.sub(r"\[[^\]]*\]", " ", cell.replace("**", "").replace("`", "")).strip()
    return re.split(r"[\s（(，,、]", t, maxsplit=1)[0] if t else ""


def manager_rows(root: Path):
    """collab.md「主管」段（舊 coordination「主管名單」）：([(名稱, 範圍, peer 欄)], 有沒有解析不出名稱的列)。

    表格第一列是表頭；peer 欄依表頭找（vault 擴充欄，team 格式 `| 主管 | 範圍 | 上層 | 上線 |` 沒有 → 空字串）。舊格式「# 目前主管」只看標題下第一個非空、非註解行，
    取第一個 token，抓不到就是抓不到，不往下找（B2：往下找會抓到說明裡的 `llm-wiki:wiki-collabteam`）。
    檔不存在／沒這段都回 ([], False)，不拋例外：其他 vault 不一定有 coordination.md。
    """
    try:
        text = collab_path(root).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], False
    out, bad, inside, header_seen, first_line, peer_at = [], False, False, False, True, None
    for ln in strip_comments(text).splitlines():
        if MANAGER_SECTION.match(ln):
            inside = True
            continue
        if not inside:
            continue
        if NEXT_HEADING.match(ln):
            break
        st = ln.strip()
        if not st:
            continue
        if st.startswith("|"):
            first_line = False
            cells = [c.strip() for c in st.strip("|").split("|")]
            if not header_seen:
                header_seen = True
                peer_at = next((i for i, c in enumerate(cells) if "peer" in c.lower()), None)
                continue
            if SEPARATOR_ROW.match(st):
                continue
            name = manager_name(cells[0]) if cells else ""
            if name:
                peers = cells[peer_at] if peer_at is not None and len(cells) > peer_at else ""
                out.append((name, cells[1] if len(cells) > 1 else "", peers))
            else:
                bad = True
        elif first_line:
            first_line = False
            name = manager_name(st)
            if name:
                out.append((name, "", ""))
            break  # 舊格式只有一位
    return out, bad


def managers(root: Path):
    """coordination.md 主管段的每位主管：[(名稱, 範圍, peer 欄)]。"""
    return manager_rows(root)[0]


def current_manager(root: Path, agent: str = "", card_team: str = ""):
    """這個 agent 該掛在哪位主管底下（辦公室 team 要的 ListAgents 名稱），判斷不出回 None。

    卡上 `office_team: 主管` 是佔位語意，手寫會在下次換主管時過期，所以由 coordination.md 推導（2026-10-12 #144 選丙）。
    多主管時依序：peer 欄有這個 agent → 卡上 office_team 對得到的那位 → 只有一位 →
    唯一一位範圍空白（並存時＝沒被別人範圍涵蓋的其餘，主管 office 2026-10-26 裁示）的 → 否則 None。
    有任何列解析不出主管名時不走後兩個退路：少算了一位，「只有一位」「唯一空白」都可能是錯的。
    """
    ms, bad = manager_rows(root)
    if not ms:
        return None
    for name, _, peers in ms:
        if agent and re.search(rf"(?<![\w-]){re.escape(agent)}(?![\w-])", peers):
            return name
    for name, _, _ in ms:
        if card_team and card_team == name:
            return name
    if bad:
        return None
    if len(ms) == 1:
        return ms[0][0]
    whole = [name for name, scope, _ in ms if not scope or scope in ("—", "-")]
    return whole[0] if len(whole) == 1 else None


def strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def must_reads(body: str):
    """必讀的檔案路徑（不含 #標題）：新格式是「## 必讀」整段，舊卡是「- 必讀」底下縮排的項目。

    每行取第一個 [[連結]] 或 `路徑`；含 <…> 的是範本佔位符，略過。
    """
    if re.search(r"^## 必讀\s*$", body, re.M):
        # 只認「- [[…]]」「- `…`」開頭的條目；說明句裡順手提到的 `collab.md` 不是必讀（AEGIVERSE 卡「接手時讀什麼：不讀…」）
        lines = [ln for ln in section(body, "必讀").split("\n") if re.match(r"^\s*- (\[\[|`)", ln)]
    else:
        lines = _old_must_read_lines(body)
    out = []
    for ln in lines:
        m = WIKILINK.search(ln)
        b = re.search(r"`([^`<>]+)`", ln)
        if m and "<" not in m.group(1):
            out.append(m.group(1).strip())
        elif b:
            out.append(b.group(1).strip())
    return out


def _old_must_read_lines(body: str):
    out, inside = [], False
    for ln in strip_comments(body).split("\n"):
        if re.match(r"^- .*必讀", ln):
            inside = True
            continue
        if inside and re.match(r"^(- |#)", ln):
            break
        if inside:
            out.append(ln)
    return out


def section(body: str, title: str) -> str:
    m = re.search(rf"^## {title}\s*\n(.*?)(?=^## |\Z)", strip_comments(body), re.S | re.M)
    return m.group(1) if m else ""


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


def copied_lines(text: str):
    """沒有指向出處（[[連結]] 或 `路徑`）又超過 40 字的條目：多半是把 _README 的內容抄過來了。

    看最後一筆檢查點（舊卡是「進行中事項」）；只看「- 」開頭的行。
    """
    out = []
    for ln in text.split("\n"):
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
    return roles_dir(root) / f"{role}.md"


def checkpoint_path(root: Path, role: str) -> Path:
    return root / CHECKPOINTS_REL / f"{role}.md"


def last_checkpoint(root: Path, role: str, body: str = "") -> str:
    """最後一筆檢查點（「## 」開頭那段）；還沒搬的舊卡退回「進行中事項」段。"""
    p = checkpoint_path(root, role)
    if p.is_file():
        parts = re.split(r"(?m)^(?=## )", strip_comments(p.read_text(encoding="utf-8", errors="replace")))
        entries = [x for x in parts if x.startswith("## ")]
        return entries[-1].rstrip() if entries else ""
    return section(body, "進行中事項").strip()


def checkpoint_date(entry: str) -> str:
    m = re.match(r"## (\d{4}-\d{2}-\d{2})", entry)
    return m.group(1) if m else ("舊卡" if entry else "—")


def holders(root: Path):
    """collab.md「在線」（舊 coordination「Session 狀態」）：[(session, 角色欄)]。主管寫的，本腳本只讀。"""
    try:
        text = collab_path(root).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out, inside, header = [], False, False
    for ln in strip_comments(text).splitlines():
        if ONLINE_SECTION.match(ln):
            inside, header = True, False
            continue
        if not inside:
            continue
        if NEXT_HEADING.match(ln):
            break
        st = ln.strip()
        if not st.startswith("|") or SEPARATOR_ROW.match(st):
            continue
        if not header:
            header = True
            continue
        cells = [c.strip() for c in st.strip("|").split("|")]
        if len(cells) >= 2:
            # 整個名稱連 [ref] 一起留（SendMessage 要用；名稱可能有空白，如「Chrome 操作 [fa5391]」），切在全形註記前
            name = re.split(r"[（(]", cells[0].replace("**", "").replace("`", ""), maxsplit=1)[0].strip()
            out.append((name, cells[1]))
    return out


def holder_of(root: Path, role: str, rows=None) -> str:
    for session, roles in (holders(root) if rows is None else rows):
        if re.search(rf"(?<![\w-]){re.escape(role)}(?![\w-])", roles):
            return session
    return ""


def load(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    fields, _, body = split_frontmatter(text)
    return text, fields, body


# roles/ 底下預期會有、但不是角色卡的檔。報它們等於每個 vault 都唸一次（ISS-007 的 A8）
NOT_A_CARD = {"README.md"}


def all_cards(root: Path):
    """角色卡 ＝ frontmatter 有 `role:` 的檔。**正面判準，不是排除法。**

    舊版用「檔名不以 `_` 開頭」排除，於是 1.5.2 加進樣板的 `roles/README.md`
    被列成一個叫「README」的角色（ISS-007）。排除法每多一種非卡文件就要補一條，
    正面判準一次解決。
    """
    return [p for p, _f in _scan(root)[0]]


def _scan(root: Path):
    """回 (卡, 被排除的)。被排除的要講出來 —— 卡漏寫 `role:` 而靜默消失，
    比多列一個 README 危險（接手的人會以為沒人持有那個角色）。"""
    d = roles_dir(root)
    if not d.is_dir():
        return [], []
    cards, skipped = [], []
    for q in sorted(q for q in d.glob("*.md") if not q.name.startswith("_")):
        _, f, _ = load(q)
        if f.get("role"):
            cards.append((q, f))
        elif q.name not in NOT_A_CARD:
            skipped.append(q)
    return cards, skipped


def _print_skipped(root: Path, skipped):
    if not skipped:
        return
    names = "、".join(q.name for q in skipped)
    print(f"{chr(9888)}️ {roles_dir(root).relative_to(root).as_posix()}/ 底下 {len(skipped)} 個檔沒有 `role:`，未列入：{names}")
    print("   —— 不是角色卡就沒關係；是角色卡請補 frontmatter 的 `role:`")


def card_problems(root: Path, path: Path, body: str):
    role = load(path)[1].get("role") or path.stem
    reads = must_reads(body)
    out = []
    if len(reads) > MAX_MUST_READ:
        out.append(f"必讀 {len(reads)} 份 > {MAX_MUST_READ}")
    out += [f"必讀找不到：{r}" for r in reads if resolve(root, r) is None and not Path(r).exists()]
    last = last_checkpoint(root, role, body)
    out += [p for p in link_problems(root, body + "\n" + last) if not any(p.startswith(f"[[{r}]]") for r in reads)]
    out += [f"疑似抄了 _README（沒有指向出處）：{c}" for c in copied_lines(last)]
    if path.parent == root / OLD_ROLES_REL:
        out.append(f"還在舊位置 {OLD_ROLES_REL}/：跑 role_cards.py migrate")
    return out


def cmd_list(root: Path) -> int:
    pairs, skipped = _scan(root)
    if not pairs:
        _print_skipped(root, skipped)
        print(f"沒有角色卡（{ROLES_REL}/ 不存在或是空的）。建卡：python role_cards.py new <角色>")
        return 0
    rows = holders(root)
    print("| 角色 | 持有者（collab.md 在線） | 職稱 | 必讀 | 最後檢查點 | 注意 |")
    print("|---|---|---|---|---|---|")
    for p, f in pairs:
        _, _, body = load(p)
        role = f.get("role") or p.stem
        n = len(card_problems(root, p, body))
        print(f"| {role} | {holder_of(root, role, rows) or '（無人）'} | {f.get('office_title') or '—'} | {len(must_reads(body))} | "
              f"{checkpoint_date(last_checkpoint(root, role, body))} | {f'{n} 項，跑 check' if n else ''} |")
    _print_skipped(root, skipped)
    return 0


def cmd_check(root: Path, quiet: bool) -> int:
    """每張卡的連結（檔案＋標題）、必讀清單、最後一筆檢查點。斷掉的只回報，不自動修 —— 猜錯位置比斷掉更糟。"""
    total = 0
    for p in all_cards(root):
        _, _, body = load(p)
        probs = card_problems(root, p, body)
        total += len(probs)
        if probs:
            print(f"🔴 {p.relative_to(root).as_posix()}")
            for x in probs:
                print(f"   - {x}")
        elif not quiet:
            print(f"✅ {p.relative_to(root).as_posix()}")
    _print_skipped(root, _scan(root)[1])
    if total == 0 and not quiet:
        print("角色卡沒有斷掉的指標")
    return 0


def cmd_cost(root: Path, role: str) -> int:
    p = card_path(root, role)
    if not p.is_file():
        print(f"沒有這張角色卡：{p.relative_to(root).as_posix()}")
        return 1
    text, _, body = load(p)
    reads = must_reads(body)
    rows = [(p.relative_to(root).as_posix(), est_tokens(text), True)]
    for r in reads:
        f = Path(r) if Path(r).is_absolute() else resolve(root, r)
        if f is not None and f.is_file():
            rows.append((r, est_tokens(f.read_text(encoding="utf-8", errors="replace")), True))
        else:
            rows.append((r, 0, False))
    last = last_checkpoint(root, role, body)
    if last and checkpoint_path(root, role).is_file():
        rows.append((f"{CHECKPOINTS_REL}/{role}.md（最後一筆）", est_tokens(last), True))
    print("| 檔 | 估計 token |")
    print("|---|---|")
    for name, tok, ok in rows:
        print(f"| `{name}` | {tok if ok else '找不到'} |")
    total = sum(t for _, t, _ in rows)
    print(f"\n合計約 {total} token（粗估；不含守門腳本的輸出）")
    if len(reads) > MAX_MUST_READ:
        print(f"⚠️ 必讀 {len(reads)} 份，超過上限 {MAX_MUST_READ}：請使用者或主管精簡")
    return 0


def cmd_claim(root: Path, role: str, agent: str) -> int:
    """接手：不寫卡（team 格式的卡只放定義；誰持有由主管記在 collab.md「在線」）。

    印出最後一筆檢查點、別人是不是還掛著這個角色、辦公室登記那行。
    """
    p = card_path(root, role)
    if not p.is_file():
        print(f"沒有這張角色卡：{p.relative_to(root).as_posix()}")
        return 1
    _, fields, body = load(p)
    prev = holder_of(root, role)
    if prev and prev != agent:
        print(f"⚠️ collab.md「在線」記 {role} 由 {prev} 持有 —— 對 ListAgents，還在線就先問使用者")
    last = last_checkpoint(root, role, body)
    print(f"上次檢查點：\n{last}" if last else "上次檢查點：無")
    mgr = current_manager(root, agent)  # 卡上 reports_to 是角色名，不是 ListAgents 名稱，不參與判斷
    print("辦公室登記（有 pixel-office 才跑）：")
    print(f"  office_profile(agent={agent}, name={fields.get('office_name') or role}, "
          f"title={fields.get('office_title') or role}, team={mgr or 'off'})"
          + ("" if mgr else "   ← collab.md「主管」判斷不出你屬於哪位主管"))
    if mgr:
        print(f"報到：SendMessage 給 {mgr}「接手：{role}（ListAgents={agent}）」＋上次檢查點的下一步")
    return 0


def cmd_new(root: Path, role: str) -> int:
    p = root / ROLES_REL / f"{role}.md"
    if p.exists() or (root / OLD_ROLES_REL / f"{role}.md").exists():
        print(f"已經有這張卡：{role}")
        return 1
    candidates = [root / "Templates" / TEMPLATE, Path(__file__).resolve().parent.parent / "templates" / "vault" / "Templates" / TEMPLATE]
    tpl = next((c for c in candidates if c.is_file() and "## 職責" in c.read_text(encoding="utf-8")), None)
    if tpl is None:
        print(f"找不到 team 格式的範本 {TEMPLATE}")
        return 1
    text = tpl.read_text(encoding="utf-8").replace("<角色名>", role, 1)
    ensure_office(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    print(f"已建卡：{p.relative_to(root).as_posix()}（請填職責、邊界、必讀、可用 skill、交付）")
    return 0


# ── migrate：舊 wiki/meta/ → .claude/office/ ──────────────────────────────

OFFICE_GITIGNORE = "collab.md\ncheckpoints/\n"
# 舊卡「## 定義」底下的條目 → 新卡哪一段。沒對到的多半是 🔴 規則，進「邊界」
OLD_ITEM_SECTION = (
    (re.compile(r"^- 職責"), "職責"),
    (re.compile(r"^- (?:必讀|接手時讀)"), "必讀"),
    (re.compile(r"^- 用到才查"), "用到才查"),
    (re.compile(r"^- 守門腳本"), "守門腳本"),
)
NEW_SECTIONS = ("職責", "邊界", "必讀", "用到才查", "守門腳本", "可用 skill", "交付")


def ensure_office(root: Path):
    d = root / OFFICE_REL
    d.mkdir(parents=True, exist_ok=True)
    gi = d / ".gitignore"
    if not gi.exists():
        gi.write_text(OFFICE_GITIGNORE, encoding="utf-8")


def _old_items(definition: str):
    """「## 定義」→ [(新段名, 條目原文)]；一個條目＝「- 」開頭那行＋底下縮排的行。"""
    items, cur = [], None
    for ln in definition.split("\n"):
        if ln.startswith("- "):
            cur = [ln]
            items.append(cur)
        elif cur is not None and (ln.startswith((" ", "\t")) or not ln.strip()):
            cur.append(ln)
    out = []
    for lines in items:
        text = "\n".join(lines).rstrip()
        name = next((n for rx, n in OLD_ITEM_SECTION if rx.match(text)), "邊界")
        out.append((name, text))
    return out


def convert_card(text: str, today: str):
    """舊卡 → (新卡原文, 檢查點第一筆或 "")。原文一字不改，只重新歸段。"""
    fields, _, body = split_frontmatter(text)
    role = fields.get("role", "")
    grouped = {n: [] for n in NEW_SECTIONS}
    for name, item in _old_items(section(body, "定義")):
        if name == "職責":
            item = re.sub(r"^- 職責範圍：\s*", "", item, count=1)
        grouped[name].append(item)
    grouped["可用 skill"] = grouped["可用 skill"] or ["無"]
    grouped["交付"] = grouped["交付"] or ["（舊卡沒有這段，使用者補）"]
    fm = [f"role: {role}", "source: 使用者指定", "layer: 1", "reports_to: 主管"]
    fm += [f"{k}: {fields[k]}" for k in ("office_name", "office_title") if fields.get(k)]
    out = ["---", *fm, "---",
           f"<!-- 角色卡（pixel-office skill team 格式）：只放定義，使用者或主管維護。做到哪寫 {CHECKPOINTS_REL}/{role}.md。"
           f"{today} 由 role_cards.py migrate 從 {OLD_ROLES_REL}/ 搬來，原文未改寫。 -->", ""]
    for n in NEW_SECTIONS:
        if grouped[n]:
            out += [f"## {n}", *grouped[n], ""]
    progress = [ln for ln in section(body, "進行中事項").strip().split("\n") if ln.strip() and ln.strip() != "-"]
    cp = ""
    if progress:
        cp = "\n".join([f"## {today} migrate", "- 做完：（舊卡「進行中事項」原文搬入，未改寫）", "- 卡在：見下一步各行", "- 下一步：",
                        *("  " + ln for ln in progress)]) + "\n"
    return "\n".join(out).rstrip() + "\n", cp


def convert_coordination(text: str) -> str:
    """舊 coordination.md → collab.md：標題「主管名單／目前主管」→「主管」、「Session 狀態」→「在線」，其餘原樣。"""
    text = re.sub(r"(?m)^#\s*(?:主管名單|目前主管)\s*$", "# 主管", text)
    return re.sub(r"(?m)^#\s*Session 狀態\s*$", "# 在線", text)


def cmd_migrate(root: Path, dry: bool) -> int:
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    plan = []
    old_roles = root / OLD_ROLES_REL
    for q in sorted(old_roles.glob("*.md")) if old_roles.is_dir() else []:
        f = load(q)[1]
        if not f.get("role"):
            plan.append(("skip", q, None, None))
            continue
        dst = root / ROLES_REL / f"{f['role']}.md"
        if dst.exists():
            plan.append(("exists", q, dst, None))
            continue
        plan.append(("card", q, dst, convert_card(q.read_text(encoding="utf-8", errors="replace"), today)))
    old_coord, new_coord = root / OLD_COORD_REL, root / COLLAB_REL
    if old_coord.is_file():
        plan.append(("exists" if new_coord.exists() else "coord", old_coord, new_coord, None))
    if not plan:
        print(f"沒有要搬的（{OLD_ROLES_REL}/、{OLD_COORD_REL} 都不存在）")
        return 0
    for kind, src, dst, conv in plan:
        rel = src.relative_to(root).as_posix()
        if kind == "skip":
            print(f"略過 {rel}（不是角色卡；搬完沒用就刪）")
        elif kind == "exists":
            print(f"⚠️ {dst.relative_to(root).as_posix()} 已存在，{rel} 不動 —— 人工比對")
        elif kind == "card":
            note = f"＋檢查點 {CHECKPOINTS_REL}/{dst.stem}.md" if conv[1] else ""
            print(f"{rel} → {dst.relative_to(root).as_posix()}{note}")
        else:
            print(f"{rel} → {COLLAB_REL}（標題改「主管」「在線」）")
    if dry:
        print("\n--dry-run：沒有寫任何檔")
        return 0
    ensure_office(root)
    for kind, src, dst, conv in plan:
        if kind == "card":
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(conv[0], encoding="utf-8")
            if conv[1]:
                cp = checkpoint_path(root, dst.stem)
                cp.parent.mkdir(parents=True, exist_ok=True)
                with cp.open("a", encoding="utf-8") as fh:
                    fh.write(conv[1])
            src.unlink()
        elif kind == "coord":
            dst.write_text(convert_coordination(src.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
            src.unlink()
    print(f"\n已搬。{ROLES_REL}/ 進 git；collab.md 與 checkpoints/ 被 {OFFICE_REL}/.gitignore 排除；舊路徑在 git 顯示刪除")
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
    if cmd == "migrate":
        return cmd_migrate(root, "--dry-run" in args)
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
