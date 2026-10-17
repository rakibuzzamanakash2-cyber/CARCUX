"""The claim sheet: an Excel workbook in which a person restates each fact-checked claim
neutrally and confirms the fact-checker's verdict, and its checker.

The tool fills in what it can read (link, date, title, verdict words, scope hint); the
person fills the rest from the article. Nothing in the person's columns is filled by a
program.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

AUTO = ["factcheck_id", "fact_checker", "published_at", "url", "title", "verdict_hint",
        "scope_hint"]  # fmt: skip
PERSON = ["in_scope", "same_claim_as", "claim", "claim_type", "event_type", "place",
          "event_date", "verdict", "evidence_tier", "checked_by", "notes"]  # fmt: skip
COLUMNS = AUTO + PERSON

CHOICES = {
    "in_scope": ["yes", "no"],
    "claim_type": [
        "occurrence",
        "count",
        "attribution",
        "media_authenticity",
        "official_action",
    ],  # fmt: skip
    "event_type": [
        "protest",
        "armed_violence",
        "mob_violence",
        "arson",
        "attack_on_place_of_worship",
        "communications_shutdown",
        "curfew",
        "mass_arrest",
        "publication",
        "official_statement",
        "other",
    ],  # fmt: skip
    "verdict": [
        "false",
        "misleading",
        "altered",
        "partly_false",
        "partly_true",
        "true",
        "unproven",
    ],  # fmt: skip
    "evidence_tier": ["B", "C"],
}

HOW_TO = [
    ("What this is", "One row per fact-check published 1 July–15 August 2024. Grey columns "
     "were filled by the indexer; fill the white ones by reading the article (the link)."),
    ("in_scope", "yes if the fact-check is about an event of the July–August 2024 uprising or "
     "its aftermath (to 15 August); otherwise no, and leave the rest blank."),
    ("same_claim_as", "If another row checks the same claim (another fact-checker, or the "
     "English version), put that row's factcheck_id here and leave claim blank."),
    ("claim", "The claim in one neutral sentence: what, where, when. No names of private "
     "individuals (write 'a student', 'a man'); organisations may be named. Not the "
     "verdict: 'Seven people were killed at Kotbari, Cumilla on 18 July', not 'False claim "
     "that…'."),
    ("claim_type", "occurrence: something happened. count: how many died, were hurt, … "
     "attribution: an outlet or official said something. media_authenticity: a photo or "
     "video shows what it is said to show. official_action: a curfew, shutdown, order."),
    ("event_type", "The kind of event the claim is about. Never a side or a party."),
    ("place, event_date", "As the claim states them (district or place name; YYYY-MM-DD)."),
    ("verdict", "The fact-checker's verdict, as the article states it. Not your own view. "
     "If the article does not give one, leave blank."),
    ("evidence_tier", "B if the fact-check rests on primary evidence (hospital or official "
     "record, the misquoted outlet itself, the original footage). C if only on other "
     "reports. (Tier A is the UN report, recorded separately.)"),
    ("checked_by", "Your annotator pseudonym, never your name."),
    ("Privacy", "Do not copy post text, names, handles or phone numbers into the sheet. Links "
     "to social media posts are kept by the indexer in restricted/, not here."),
]  # fmt: skip


def write_sheet(records: list[dict], path: Path) -> int:
    wb = Workbook()
    ws = wb.active
    ws.title = "Claims"
    ws.append(COLUMNS)
    grey = PatternFill("solid", fgColor="E7E6E6")
    head = PatternFill("solid", fgColor="1F5F3A")
    for i in range(1, len(COLUMNS) + 1):
        c = ws.cell(row=1, column=i)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = head
    rows = sorted(records, key=lambda r: (not r["scope_hint"], r["published_at"] or ""))
    for r in rows:
        ws.append([r["factcheck_id"], r["fact_checker"], (r["published_at"] or "")[:10],
                   r["url"], r["title"], r["verdict_hint"] or "",
                   "likely" if r["scope_hint"] else ""] + [""] * len(PERSON))  # fmt: skip
    for row in ws.iter_rows(min_row=2, max_col=len(AUTO)):
        for c in row:
            c.fill = grey
    widths = {"factcheck_id": 22, "url": 30, "title": 60, "claim": 60, "notes": 30}
    for i, name in enumerate(COLUMNS, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = widths.get(name, 15)
    ws.freeze_panes = "B2"
    last = max(2, len(rows) + 1)
    lists = wb.create_sheet("Lists")
    for j, (name, values) in enumerate(CHOICES.items(), start=1):
        col = lists.cell(row=1, column=j).column_letter
        lists.cell(row=1, column=j, value=name)
        for k, v in enumerate(values, start=2):
            lists.cell(row=k, column=j, value=v)
        dv = DataValidation(type="list", formula1=f"=Lists!${col}$2:${col}${len(values) + 1}",
                            allow_blank=True)  # fmt: skip
        target = ws.cell(row=1, column=COLUMNS.index(name) + 1).column_letter
        dv.add(f"{target}2:{target}{last}")
        ws.add_data_validation(dv)
    how = wb.create_sheet("How to fill", 0)
    how.column_dimensions["A"].width = 22
    how.column_dimensions["B"].width = 110
    for a, b in HOW_TO:
        how.append([a, b])
    for row in how.iter_rows():
        row[0].font = Font(bold=True)
        row[1].alignment = Alignment(wrap_text=True, vertical="top")
    wb.active = 1
    wb.save(path)
    return len(rows)


def check_sheet(path: Path) -> list[str]:
    """Problems in a filled sheet, by row. Empty when it is ready to convert."""
    ws = load_workbook(path, read_only=True)["Claims"]
    rows = list(ws.iter_rows(values_only=True))
    header = list(rows[0])
    missing = [c for c in COLUMNS if c not in header]
    if missing:
        return [f"columns missing: {', '.join(missing)}"]
    col = {name: header.index(name) for name in COLUMNS}
    ids = {r[col["factcheck_id"]] for r in rows[1:]}
    problems = []
    for n, r in enumerate(rows[1:], start=2):

        def v(name, r=r):
            x = r[col[name]]
            return str(x).strip() if x is not None else ""

        if v("in_scope") != "yes":
            continue
        where = f"row {n} ({v('factcheck_id')})"
        for name, allowed in CHOICES.items():
            if v(name) and v(name) not in allowed and name != "in_scope":
                problems.append(f"{where}: {name} '{v(name)}' is not one of the choices")
        if v("same_claim_as"):
            if v("same_claim_as") not in ids:
                problems.append(f"{where}: same_claim_as names an unknown row")
            continue
        for name in ("claim", "claim_type", "event_type", "event_date", "checked_by"):
            if not v(name):
                problems.append(f"{where}: {name} is empty")
        if v("event_date") and not (len(v("event_date")) >= 10 and v("event_date")[4] == "-"):
            problems.append(f"{where}: event_date should be YYYY-MM-DD")
    return problems
