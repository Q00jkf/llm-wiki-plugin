#!/usr/bin/env python3
"""agenda_xml —— MS Project XML（MSPDI）共用：元素順序、自訂欄位、XSD 自驗（2026-10-16）

為什麼：agenda.md 是唯一主控（使用者 2026-10-16 定案），agenda-gantt.py 匯出的 XML 要讓 ProjectLibre、
MS Project、之後的自製甘特圖都能讀 → 寫出一律照官方 XSD（ref/mspdi_pj12.xsd）的 sequence 順序、不用任何程式的擴充，
寫出前自驗。讀入端（agenda-gantt.py read_xml）寬鬆，容許 ProjectLibre 的非標準輸出。

XSD 來源副本的 targetNamespace 是 …/project/2007，實際 MSPDI 檔用 http://schemas.microsoft.com/project
→ 驗證時在記憶體換成後者（只換命名空間、不動結構）。

自訂欄位 FieldID 依 learn.microsoft.com PjField 列舉（2026-10-16 核對）。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XSD = ROOT / "raw" / "manager" / "schedule" / "ref" / "mspdi_pj12.xsd"
NS = "http://schemas.microsoft.com/project"

# 欄位鍵 → (FieldID, FieldName, 別名)
FIELDS = {
    "type": ("188743731", "Text1", "類型"),
    "tags": ("188743734", "Text2", "標籤"),
    "ref": ("188743737", "Text3", "出處"),
    "rule": ("188743740", "Text4", "重複規則"),
    "id": ("188743743", "Text5", "代號"),
}

# XSD sequence 順序（只列會寫的元素；順序錯 XSD 驗證會擋）
PROJECT_ORDER = ("SaveVersion", "Name", "Title", "LastSaved", "ScheduleFromStart", "StartDate", "CurrencyCode", "CalendarUID",
                 "DefaultStartTime", "DefaultFinishTime", "MinutesPerDay", "MinutesPerWeek", "DaysPerMonth",
                 "ExtendedAttributes", "Calendars", "Tasks")
TASK_ORDER = ("UID", "ID", "Name", "OutlineNumber", "OutlineLevel", "Start", "Finish", "Duration", "DurationFormat",
              "Milestone", "Summary", "PercentComplete", "ActualFinish", "ConstraintType", "ConstraintDate", "Deadline", "Notes",
              "PredecessorLink", "ExtendedAttribute", "Baseline")


def sort_children(el, order):
    """子元素依 XSD 順序重排（同名元素保持原相對順序）。"""
    rank = {t: i for i, t in enumerate(order)}
    kids = list(el)
    for k in kids:
        el.remove(k)
    for k in sorted(kids, key=lambda k: rank.get(k.tag.split("}")[-1], len(order))):
        el.append(k)


_schema = None


def validate(data):
    """XSD 驗證 bytes；回傳錯誤清單（空＝通過）。沒裝 lxml 或 vault 沒放 XSD 副本回 None（未驗）。"""
    global _schema
    try:
        from lxml import etree
    except ImportError:
        return None
    if not XSD.is_file():
        return None
    if _schema is None:
        xsd = XSD.read_bytes().replace(NS.encode() + b"/2007", NS.encode())
        _schema = etree.XMLSchema(etree.fromstring(xsd))
    if _schema.validate(etree.fromstring(data)):
        return []
    return [f"L{e.line}: {e.message}" for e in _schema.error_log][:10]
