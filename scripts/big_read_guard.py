#!/usr/bin/env python3
"""PreToolUse 守門：擋掉「整份讀大檔」，強制切片讀。

為什麼要硬擋：知識庫的 log.md 這類檔設計上只增不減，靠「沒人整份讀它」的慣例撐著。
慣例不是保護 —— 任何一次整份 Read 就是數十 k tokens，沒有任何機制擋得住。

門檻可在 vault 的 raw/.manifest.json 設定：
    "config": { "big_read_limit_bytes": 100000, "max_slice_lines": 2000 }

exit code 一律 0 —— 擋不擋靠輸出的 JSON，不是 exit code。
腳本自身出錯時放行（fail-open）：守門壞掉不該讓整個 session 動不了。

🔴 這個守門能擋什麼、不能擋什麼（誠實說明，勿刪）：
  能擋：無參數的 `Read <大檔>`、limit 大到等於整份讀、**PDF 沒帶 pages**（PDF 的 limit 不是切片）—— 最常見的手滑。
  擋不住：
    · Bash（cat / sed / python -c open().read()）—— matcher 只有 "Read"
    · Grep 的回傳量 —— 完全不在守門範圍，而檔越大 grep 回得越多
    · session 層級的指示（例如「優先用 Bash 讀檔」）可直接讓它失效
  所以它是**減速丘，不是保證**。把它當保證比沒有它更危險 —— 會讓人停止警戒。
"""
import json
import os
import sys
from pathlib import Path

DEFAULT_LIMIT_BYTES = 100_000   # 約 30k tokens（中文約 1 tok/字）
DEFAULT_MAX_SLICE = 2000        # 與 Read 工具預設上限同量級；超過即視為整份讀

for stream in (sys.stdout, sys.stdin):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


def load_config():
    """從 vault manifest 讀門檻。找不到就用預設值。"""
    limit, slice_max = DEFAULT_LIMIT_BYTES, DEFAULT_MAX_SLICE
    start = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    cur = Path(start).resolve()
    for _ in range(6):
        m = cur / "raw" / ".manifest.json"
        if m.is_file():
            try:
                with m.open(encoding="utf-8") as f:
                    cfg = json.load(f).get("config", {})
                limit = int(cfg.get("big_read_limit_bytes", limit))
                slice_max = int(cfg.get("max_slice_lines", slice_max))
            except (OSError, ValueError, TypeError):
                pass
            break
        if cur.parent == cur:
            break
        cur = cur.parent
    return limit, slice_max


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0                                    # 讀不到輸入 → 放行

    if data.get("tool_name") != "Read":
        return 0

    limit_bytes, max_slice = load_config()
    ti = data.get("tool_input") or {}
    path = ti.get("file_path") or ""
    is_pdf = path.lower().endswith(".pdf")

    # PDF：Read 對 PDF 不理會 offset／limit（limit=50 仍回整份文字＋整頁渲染圖），
    # 真正的切片參數是 pages=。所以 PDF 只認 pages，不認 limit（2026-09-21 驗收實測）。
    if is_pdf:
        if ti.get("pages"):
            return 0                                # 有 pages ＝ 真切片（Read 自己限 20 頁）
    else:
        limit = ti.get("limit")
        if limit is not None:
            try:
                if int(limit) <= max_slice:
                    return 0                        # 真正的切片，放行
            except (TypeError, ValueError):
                return 0                            # limit 不是數字 → 不臆測，放行
            # limit 過大 → 落到下面的大小判定，照樣擋
        elif ti.get("offset") is not None:
            return 0                                # 只帶 offset，放行

    if not path:
        return 0
    try:
        size = os.path.getsize(path)
    except OSError:
        return 0                                    # 檔不存在 → 交給 Read 自己報錯

    if size <= limit_bytes:
        return 0

    name = os.path.basename(path)
    ktok = size // 3400
    if is_pdf:
        deny(
            f"🔴 `{name}` 是 {size:,} bytes 的 PDF，未帶 pages 等於整份讀（文字＋每頁渲染圖，≥{ktok:,}k tokens）。\n"
            f"PDF 的切片參數是 pages，offset／limit 對 PDF 無效（limit=50 一樣回整份）：\n"
            f"  · 先看目錄／前幾頁 → Read pages=\"1-3\"\n"
            f"  · 要某一節 → Read pages=\"N-M\"（一次 ≤20 頁）\n"
            f"  · 要全文檢索 → 先抽成文字檔再 Grep：Bash `python -c \"import pypdf,sys;print('\\n'.join(p.extract_text() or '' for p in pypdf.PdfReader(sys.argv[1]).pages))\" \"{path}\" > \"{path}.txt\"`（沒有 pypdf 就 `pdftotext`）\n"
            f"🔴 不要用 limit／offset 繞過 —— 對 PDF 它不是切片，是整份。真的需要整份，請先跟使用者說明理由。"
        )
        return 0
    deny(
        f"🔴 `{name}` 有 {size:,} bytes（約 {ktok:,}k tokens），"
        f"禁止整份讀（上限 {limit_bytes:,} bytes）。\n"
        f"改用切片或搜尋：\n"
        f"  · 找特定內容 → Grep pattern=\"關鍵字\" path=\"{path}\"\n"
        f"  · 看最近的   → Bash: tail -60 \"{path}\"\n"
        f"  · 真的要讀某段 → Read 帶 offset ＋ limit（≤{max_slice} 行）\n"
        f"  · 只是要附加 → 純文字檔可 Bash `cat >>`，二進位檔不可\n"
        f"🔴 不要改用其他工具繞過 —— 那不是取巧，是把 {ktok:,}k tokens 灌進 context，"
        f"本檔擋的就是這件事。真的需要整份，請先跟使用者說明理由。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
