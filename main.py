import re
from dataclasses import dataclass
from typing import Optional

import fitz
import pdfplumber

DAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
REVERSED_TO_DAY = {day[::-1]: day for day in DAYS}

# International worker PDFs use English abbreviations with Hebrew ordinal letter
ENG_TO_DAY = {
    "Sun-א": "ראשון",
    "Mon-ב": "שני",
    "Tue-ג": "שלישי",
    "Wed-ד": "רביעי",
    "Thu-ה": "חמישי",
    "Fri-ו": "שישי",
    "Sat-ש": "שבת",
}

CELL_TO_DAY = {**REVERSED_TO_DAY, **ENG_TO_DAY}
TIME_PATTERN = re.compile(r"\d{1,2}:\d{2}")

COL_PATIENT_SIG = 0
COL_WORKER_SIG = 1
COL_HOL = 7
COL_DAY_NAME = 8

DOT_RADIUS = 1.2
DASH_WIDTH = 1.0
CIRCLE_X_RADIUS = 4.5
BLACK = (0, 0, 0)


def is_holiday(cell: Optional[str]) -> bool:
    return bool(cell and "גח" in cell)


def normalize_time(cell: Optional[str]) -> Optional[str]:
    if not cell:
        return None
    times = TIME_PATTERN.findall(cell)
    if len(times) >= 2:
        return f"{times[0]}-{times[1]}"
    return times[0] if times else None


def extract_schedule(tables: list) -> dict:
    for table in tables:
        header_row = None
        for row in table:
            clean = [cell.strip() if cell else "" for cell in row]
            if any(token in CELL_TO_DAY for token in clean):
                header_row = clean
                break
        if header_row is None:
            continue

        col_to_day = {
            col: CELL_TO_DAY[cell]
            for col, cell in enumerate(header_row)
            if cell in CELL_TO_DAY
        }
        header_idx = next(
            i for i, row in enumerate(table)
            if any((cell or "").strip() in CELL_TO_DAY for cell in row)
        )
        time_row = table[header_idx + 1] if header_idx + 1 < len(table) else []

        schedule = {}
        for col, day in col_to_day.items():
            raw = time_row[col] if col < len(time_row) else None
            time_val = normalize_time(raw)
            schedule[day] = {"working": time_val is not None, "time": time_val}
        return schedule

    return {}


@dataclass
class RowInfo:
    worker_bbox: Optional[tuple]   # worker-signature cell bbox
    patient_bbox: Optional[tuple]  # set only on first row of each week group
    is_working: bool
    is_holiday: bool
    group_id: int


def classify_rows(table_obj, table_data: list, schedule: dict, first_day: int = 1, last_day: int = 31) -> list[RowInfo]:
    rows: list[RowInfo] = []
    group_id = -1

    for row_idx in range(1, len(table_data)):
        row_data = table_data[row_idx]
        if len(row_data) <= COL_DAY_NAME:
            continue
        day_num_str = (row_data[9] or "").strip()
        if not day_num_str.isdigit():
            continue
        day_num = int(day_num_str)
        if day_num < first_day or day_num > last_day:
            continue

        row_obj = table_obj.rows[row_idx] if row_idx < len(table_obj.rows) else None

        # New week group whenever patient-sig column has a non-None cell
        patient_bbox = None
        if row_data[COL_PATIENT_SIG] is not None:
            group_id += 1
            if row_obj:
                patient_bbox = row_obj.cells[COL_PATIENT_SIG]

        day_raw = (row_data[COL_DAY_NAME] or "").strip()
        day_name = CELL_TO_DAY.get(day_raw)
        hol = is_holiday(row_data[COL_HOL] if COL_HOL < len(row_data) else None)
        working = bool(day_name and schedule.get(day_name, {}).get("working"))

        worker_bbox = None
        if row_obj:
            worker_bbox = row_obj.cells[COL_WORKER_SIG]

        rows.append(RowInfo(
            worker_bbox=worker_bbox,
            patient_bbox=patient_bbox,
            is_working=working,
            is_holiday=hol,
            group_id=group_id,
        ))

    return rows


def plan_marks(rows: list[RowInfo]) -> list[tuple[tuple, str]]:
    marks: list[tuple[tuple, str]] = []

    free_slots = [
        r.worker_bbox for r in rows
        if r.worker_bbox and not r.is_working and not r.is_holiday
    ]
    free_iter = iter(free_slots)

    # Track which groups get at least one dot (by the worker_bbox of the dot)
    dot_bboxes: set[tuple] = set()

    for row in rows:
        if not row.worker_bbox:
            continue
        if row.is_holiday:
            marks.append((row.worker_bbox, "dash"))
            if row.is_working:
                slot = next(free_iter, None)
                if slot:
                    marks.append((slot, "asterisk"))
                    dot_bboxes.add(slot)
        elif row.is_working:
            marks.append((row.worker_bbox, "dot"))
            dot_bboxes.add(row.worker_bbox)

    # Determine which groups had dots
    groups_with_dots: set[int] = set()
    for row in rows:
        if row.worker_bbox in dot_bboxes:
            groups_with_dots.add(row.group_id)

    # Add circle-X on patient signature cell for those groups
    seen_groups: set[int] = set()
    for row in rows:
        if row.group_id in groups_with_dots and row.patient_bbox and row.group_id not in seen_groups:
            marks.append((row.patient_bbox, "circle_x"))
            seen_groups.add(row.group_id)

    return marks


def draw_marks(fitz_page: fitz.Page, marks: list[tuple[tuple, str]]) -> None:
    for (x0, y0, x1, y1), kind in marks:
        cy = (y0 + y1) / 2

        if kind == "dot":
            cx = x1 - DOT_RADIUS - 2
            fitz_page.draw_circle(
                fitz.Point(cx, cy), DOT_RADIUS, color=BLACK, fill=BLACK
            )

        elif kind == "asterisk":
            cx = x1 - DOT_RADIUS - 2
            fitz_page.insert_text(
                fitz.Point(cx - 4, cy + 4),
                "*",
                fontsize=12,
                color=BLACK,
            )

        elif kind == "dash":
            pad = 6
            fitz_page.draw_line(
                fitz.Point(x0 + pad, cy),
                fitz.Point(x1 - pad, cy),
                color=BLACK,
                width=DASH_WIDTH,
            )

        elif kind == "circle_x":
            r = CIRCLE_X_RADIUS
            cx = (x0 + x1) / 2 + (x1 - x0) * 0.3
            fitz_page.draw_circle(fitz.Point(cx, cy), r, color=BLACK, width=0.8)
            off = r * 0.6
            fitz_page.draw_line(
                fitz.Point(cx - off, cy - off), fitz.Point(cx + off, cy + off),
                color=BLACK, width=0.8,
            )
            fitz_page.draw_line(
                fitz.Point(cx - off, cy + off), fitz.Point(cx + off, cy - off),
                color=BLACK, width=0.8,
            )


def get_report_month(page) -> tuple[int, int]:
    """Return (month, year) from the 'דו"ח מעקב יומי לחדש: MM/YYYY' header cell."""
    for table in page.extract_tables():
        for row in table:
            for cell in row:
                if cell and "שדוח" in cell:
                    m = re.search(r"(\d{2})/(\d{4})", cell)
                    if m:
                        return int(m.group(1)), int(m.group(2))
    return 0, 0


def get_start_date(page) -> tuple[int, int, int]:
    """Return (day, month, year) from the row below the התחלת שיבוץ label."""
    tables = page.extract_tables()
    t0 = tables[0] if tables else []
    for r_idx, row in enumerate(t0):
        if row and row[0] and "ץוביש תלחתה" in row[0]:
            if r_idx + 1 < len(t0):
                val = (t0[r_idx + 1][0] or "").strip()
                m = re.match(r"(\d{1,2})/(\d{2})/(\d{4})", val)
                if m:
                    return int(m.group(1)), int(m.group(2)), int(m.group(3))
            break
    return 1, 0, 0


def get_end_date(page) -> tuple[int, int, int] | None:
    """Return (day, month, year) from the row below the סיום שיבוץ label, or None if absent."""
    tables = page.extract_tables()
    t0 = tables[0] if tables else []
    for r_idx, row in enumerate(t0):
        if row and row[0] and "ץוביש םויס" in row[0]:
            if r_idx + 1 < len(t0):
                val = (t0[r_idx + 1][0] or "").strip()
                m = re.match(r"(\d{1,2})/(\d{2})/(\d{4})", val)
                if m:
                    return int(m.group(1)), int(m.group(2)), int(m.group(3))
            break
    return None


def get_family_relation(page) -> str:
    """Return 'לא' or 'כן' by reading the value below the קרוב משפחה label."""
    t0_obj = page.find_tables()[0]
    # Row 13 col 0 is the label cell; the value sits just below its bottom edge
    label_bbox = t0_obj.rows[13].cells[0]
    if not label_bbox:
        return "לא"
    x0, _, x1, y1 = label_bbox
    value_text = page.crop((x0, y1, x1, y1 + 20)).extract_text() or ""
    # text is stored visually reversed; reverse to get logical Hebrew
    return value_text.strip()[::-1]


# ── Bottom-table column indices (Table 4) ───────────────────────────────────
# col0: אישור נותן השירות  col1: חתימת המטפל/ת  col2: declaration text
# col3: אישור המטפל/ת      col4: בן/בת המשפחה
BOTTOM_COL_SIG  = 1   # חתימת המטפל/ת (signature, used for declaration-row dots)
BOTTOM_COL_DECL = 2   # declaration lines (used only to identify which rows)
BOTTOM_COL_APPR = 3   # אישור המטפל/ת  (contains חתימה:)


def bottom_table_marks(t_obj, t_data: list, family_is_no: bool) -> list[tuple[tuple, str]]:
    marks: list[tuple[tuple, str]] = []

    # 1. Dot in אישור המטפל/ת → find row whose col3 cell contains :המיתח (= :חתימה)
    for row_idx, row_data in enumerate(t_data):
        cell = (row_data[BOTTOM_COL_APPR] or "") if BOTTOM_COL_APPR < len(row_data) else ""
        if "המיתח" in cell and row_idx < len(t_obj.rows):
            bbox = t_obj.rows[row_idx].cells[BOTTOM_COL_APPR]
            if bbox:
                marks.append((bbox, "dot"))
            break

    # 2. Dots in declaration column
    #    line 1 = row1  (no-relation declaration)
    #    line 2 = row2  (has-relation declaration)
    #    line 3 = row3  (not working elsewhere)
    decl_rows = {}
    for row_idx, row_data in enumerate(t_data[1:], start=1):
        cell = (row_data[BOTTOM_COL_DECL] or "") if BOTTOM_COL_DECL < len(row_data) else ""
        if not cell:
            continue
        if len(decl_rows) == 0:
            decl_rows[1] = row_idx
        elif len(decl_rows) == 1:
            decl_rows[2] = row_idx
        elif len(decl_rows) == 2:
            decl_rows[3] = row_idx
            break

    line_for_relation = 1 if family_is_no else 2
    for line_num in (line_for_relation, 3):
        row_idx = decl_rows.get(line_num)
        if row_idx is None or row_idx >= len(t_obj.rows):
            continue
        bbox = t_obj.rows[row_idx].cells[BOTTOM_COL_SIG]
        if bbox:
            marks.append((bbox, "dot"))

    return marks


def _process_page(
    plumber_page, fitz_page: fitz.Page
) -> dict:
    table_objects = plumber_page.find_tables()
    table_data_list = plumber_page.extract_tables()

    try:
        family_relation = get_family_relation(plumber_page)
    except Exception:
        family_relation = "לא"

    schedule = extract_schedule(table_data_list)
    family_is_no = family_relation == "לא"

    report_mm, report_yyyy = get_report_month(plumber_page)

    start_dd, start_mm, start_yyyy = get_start_date(plumber_page)
    first_day = (
        start_dd
        if report_yyyy == start_yyyy and report_mm == start_mm
        else 1
    )

    end = get_end_date(plumber_page)
    last_day = (
        end[0]
        if end and report_yyyy == end[2] and report_mm == end[1]
        else 31
    )

    all_marks: list[tuple[tuple, str]] = []

    for t_obj, t_data in zip(table_objects, table_data_list):
        if not t_data or not t_data[0]:
            continue
        header = t_data[0]

        if any("םוי" in (cell or "") for cell in header):
            rows = classify_rows(t_obj, t_data, schedule, first_day, last_day)
            all_marks.extend(plan_marks(rows))

        elif any("ת/לפטמה רושיא" in (cell or "") for cell in header):
            all_marks.extend(bottom_table_marks(t_obj, t_data, family_is_no))

    draw_marks(fitz_page, all_marks)

    return {
        "dots": sum(1 for _, k in all_marks if k == "dot"),
        "asterisks": sum(1 for _, k in all_marks if k == "asterisk"),
        "dashes": sum(1 for _, k in all_marks if k == "dash"),
        "circle_x": sum(1 for _, k in all_marks if k == "circle_x"),
    }


def mark_pdf(pdf_path: str, output_path: str, progress_cb=None) -> dict:
    doc = fitz.open(pdf_path)
    totals = {"dots": 0, "asterisks": 0, "dashes": 0, "circle_x": 0}

    with pdfplumber.open(pdf_path) as pdf:
        for i, plumber_page in enumerate(pdf.pages):
            stats = _process_page(plumber_page, doc[i])
            for k in totals:
                totals[k] += stats[k]
            if progress_cb:
                progress_cb(i + 1, len(pdf.pages))

    doc.save(output_path)
    return totals


if __name__ == "__main__":
    import sys
    pdf_file = sys.argv[1] if len(sys.argv) > 1 else "test.pdf"
    out = pdf_file.replace(".pdf", "_marked.pdf")
    stats = mark_pdf(pdf_file, out, progress_cb=lambda d, t: print(f"  page {d}/{t}"))
    print(f"{pdf_file} → {out}  {stats}")
