import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


DEFAULT_INPUT = "data/raw/chongqing_merged_listings.csv"
DEFAULT_OUTPUT = "data/clean/chongqing_house_cleaned.csv"
DEFAULT_REPORT = "data/clean/chongqing_house_clean_report.json"

OUTPUT_FIELDS = [
    "source",
    "city",
    "district",
    "page",
    "source_listing_id",
    "title",
    "area_m2",
    "layout",
    "room_count",
    "hall_count",
    "orientation",
    "community",
    "tags",
    "total_price_wan",
    "unit_price_yuan_m2",
    "cover_image_url",
    "is_new",
    "crawl_time",
    "dedup_key",
    "is_duplicate",
]

NON_EMPTY_FIELDS = [field for field in OUTPUT_FIELDS if field != "is_duplicate"]

VALID_ORIENTATIONS = {
    "东",
    "南",
    "西",
    "北",
    "东南",
    "东北",
    "西南",
    "西北",
    "南北",
    "东西",
}

DISTRICT_ALIASES = {
    "渝北": "两江新区",
    "江北": "两江新区",
    "双桥": "大足",
    "万盛": "綦江",
}


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    report_path = Path(args.report)

    rows = read_csv(input_path)
    cleaned_rows, report = clean_rows(
        rows,
        drop_duplicates=args.drop_duplicates,
        drop_empty_fields=not args.keep_empty_fields,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path = write_csv(output_path, cleaned_rows, OUTPUT_FIELDS)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report.update(
        {
            "input": str(input_path),
            "output": str(output_path),
            "report": str(report_path),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "drop_duplicates": args.drop_duplicates,
            "drop_empty_fields": not args.keep_empty_fields,
        }
    )
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Read {report['input_rows']} rows from {input_path}")
    print(f"Wrote {report['output_rows']} cleaned rows to {output_path}")
    print(f"Wrote cleaning report to {report_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean and normalize Chongqing second-hand house listings CSV.")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Input merged CSV path.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Cleaned CSV output path.")
    parser.add_argument("--report", default=DEFAULT_REPORT, help="JSON cleaning report output path.")
    parser.add_argument(
        "--drop-duplicates",
        action="store_true",
        help="Drop duplicate rows by dedup_key/title-area-price key. By default duplicates are kept and marked.",
    )
    parser.add_argument(
        "--keep-empty-fields",
        action="store_true",
        help="Keep rows with empty non-generated fields. By default rows with any empty field are dropped.",
    )
    return parser.parse_args()


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def write_csv(path: Path, rows: List[Dict[str, str]], fields: List[str]) -> Path:
    try:
        with path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return path
    except PermissionError:
        fallback = path.with_name(f"{path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{path.suffix}")
        with fallback.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        print(f"WARNING: {path} is locked. Wrote CSV to {fallback} instead.", file=sys.stderr)
        return fallback


def clean_rows(
    rows: List[Dict[str, str]],
    drop_duplicates: bool = False,
    drop_empty_fields: bool = True,
) -> Tuple[List[Dict[str, str]], Dict]:
    cleaned = []
    seen_keys = set()
    duplicate_count = 0
    dropped = Counter()
    source_counter = Counter()
    district_counter = Counter()

    for raw in rows:
        row = normalize_row(raw)
        source_counter[row["source"]] += 1

        if not row["title"]:
            dropped["missing_title"] += 1
            continue
        if not row["district"]:
            dropped["missing_district"] += 1
            continue
        if not row["area_m2"] or not row["total_price_wan"]:
            dropped["missing_area_or_price"] += 1
            continue

        area = to_decimal(row["area_m2"])
        total_price = to_decimal(row["total_price_wan"])
        if area is None or total_price is None:
            dropped["invalid_number"] += 1
            continue
        if area < Decimal("5") or area > Decimal("1000"):
            dropped["abnormal_area"] += 1
            continue
        if total_price < Decimal("1") or total_price > Decimal("10000"):
            dropped["abnormal_total_price"] += 1
            continue

        dedup_key = row["dedup_key"] or make_dedup_key(
            row["source"], row["source_listing_id"], row["title"], row["area_m2"], row["total_price_wan"]
        )
        row["dedup_key"] = dedup_key

        if drop_empty_fields:
            empty_fields = [field for field in NON_EMPTY_FIELDS if not row.get(field, "").strip()]
            if empty_fields:
                for field in empty_fields:
                    dropped[f"empty_{field}"] += 1
                dropped["rows_with_empty_fields"] += 1
                continue

        is_duplicate = dedup_key in seen_keys
        row["is_duplicate"] = "1" if is_duplicate else "0"
        if is_duplicate:
            duplicate_count += 1
            if drop_duplicates:
                dropped["duplicate"] += 1
                continue
        seen_keys.add(dedup_key)

        district_counter[row["district"]] += 1
        cleaned.append(row)

    missing_after = {
        field: sum(1 for row in cleaned if not row.get(field, "").strip())
        for field in OUTPUT_FIELDS
        if field != "is_duplicate"
    }

    report = {
        "input_rows": len(rows),
        "output_rows": len(cleaned),
        "dropped_rows": sum(dropped.values()),
        "drop_reasons": dict(dropped),
        "duplicates_marked": duplicate_count,
        "source_counts_before_drop": dict(source_counter),
        "district_counts": dict(district_counter),
        "missing_values_after_clean": missing_after,
    }
    return cleaned, report


def normalize_row(raw: Dict[str, str]) -> Dict[str, str]:
    row = {field: normalize_text(raw.get(field, "")) for field in OUTPUT_FIELDS}
    row["source"] = row["source"] or "unknown"
    row["city"] = row["city"] or "重庆"
    row["district"] = DISTRICT_ALIASES.get(row["district"], row["district"])
    row["page"] = normalize_int(row["page"])
    row["title"] = normalize_title(row["title"])
    row["area_m2"] = normalize_decimal(row["area_m2"], places=2)
    row["total_price_wan"] = normalize_decimal(row["total_price_wan"], places=2)
    row["unit_price_yuan_m2"] = normalize_unit_price(row["unit_price_yuan_m2"], row["total_price_wan"], row["area_m2"])
    row["layout"], row["room_count"], row["hall_count"] = normalize_layout(
        row["layout"], row["room_count"], row["hall_count"]
    )
    row["orientation"] = normalize_orientation(row["orientation"], row["tags"])
    row["community"] = normalize_text(row["community"])
    row["tags"] = normalize_tags(row["tags"])
    row["cover_image_url"] = normalize_url(row["cover_image_url"])
    row["is_new"] = "1" if row["is_new"] in {"1", "true", "True", "是", "新上", "新"} else "0"
    row["crawl_time"] = normalize_text(row["crawl_time"])
    row["source_listing_id"] = normalize_text(row["source_listing_id"])
    return row


def normalize_text(value: str) -> str:
    value = "" if value is None else str(value)
    value = value.replace("\ufeff", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_title(value: str) -> str:
    value = normalize_text(value)
    return value.strip(" -_")


def normalize_int(value: str) -> str:
    match = re.search(r"\d+", normalize_text(value))
    return str(int(match.group(0))) if match else ""


def normalize_decimal(value: str, places: int = 2) -> str:
    number = to_decimal(value)
    if number is None:
        return ""
    quant = Decimal("1") if places <= 0 else Decimal("1").scaleb(-places)
    number = number.quantize(quant, rounding=ROUND_HALF_UP)
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def normalize_unit_price(unit_price: str, total_price_wan: str, area_m2: str) -> str:
    existing = to_decimal(unit_price)
    if existing and existing > 0:
        return normalize_decimal(str(existing), places=0)
    total = to_decimal(total_price_wan)
    area = to_decimal(area_m2)
    if not total or not area or area <= 0:
        return ""
    calculated = total * Decimal("10000") / area
    return normalize_decimal(str(calculated), places=0)


def normalize_layout(layout: str, room_count: str, hall_count: str) -> Tuple[str, str, str]:
    layout = normalize_text(layout).replace(" ", "")
    room = normalize_int(room_count)
    hall = normalize_int(hall_count)
    if not room:
        match = re.search(r"(\d+)\s*室", layout)
        room = match.group(1) if match else ""
    if not hall:
        match = re.search(r"(\d+)\s*厅", layout)
        hall = match.group(1) if match else ""
    if not layout and room:
        layout = f"{room}室{hall or '0'}厅"
    return layout, room, hall


def normalize_orientation(orientation: str, tags: str) -> str:
    orientation = normalize_text(orientation).replace(" ", "")
    if orientation in VALID_ORIENTATIONS:
        return orientation
    for tag in split_tags(tags):
        tag = tag.strip()
        if tag in VALID_ORIENTATIONS:
            return tag
    return ""


def normalize_tags(tags: str) -> str:
    values = []
    seen = set()
    for tag in split_tags(tags):
        tag = normalize_text(tag)
        if not tag or tag in seen:
            continue
        seen.add(tag)
        values.append(tag)
    return "|".join(values)


def split_tags(tags: str) -> Iterable[str]:
    return re.split(r"[|,，/、]+", normalize_text(tags))


def normalize_url(value: str) -> str:
    value = normalize_text(value)
    if value.startswith("//"):
        return "https:" + value
    return value


def to_decimal(value: str):
    value = normalize_text(value)
    if not value:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", value)
    if not match:
        return None
    try:
        return Decimal(match.group(0))
    except InvalidOperation:
        return None


def make_dedup_key(*parts: str) -> str:
    raw = "|".join(normalize_text(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
