import argparse
import csv
import hashlib
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests


BASE_URL = "https://m.daojiale.com/cq/ershoufangPage"
DEFAULT_OUTPUT = "data/raw/chongqing_daojiale_listings.csv"
DEFAULT_JSONL = "data/raw/chongqing_daojiale_listings.jsonl"
DEFAULT_LOG = "data/raw/daojiale_crawl_log.csv"

USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36",
]

FIELDNAMES = [
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
]

AREA_FILTERS = [
    ("1", "渝中"),
    ("2", "沙坪坝"),
    ("4", "南岸"),
    ("5", "九龙坡"),
    ("6", "大渡口"),
    ("7", "两江新区"),
    ("8", "巴南"),
    ("9", "北碚"),
    ("10", "江津"),
    ("19", "璧山"),
    ("21", "涪陵"),
    ("22", "永川"),
    ("23", "合川"),
    ("25", "南川"),
    ("26", "武隆"),
    ("27", "丰都"),
]

DISTRICT_TO_AREA_IDS = {}
for area_id, district in AREA_FILTERS:
    DISTRICT_TO_AREA_IDS.setdefault(district, []).append(area_id)

PRICE_FILTERS = [
    ("0-100", "100万以下"),
    ("100-150", "100-150万"),
    ("150-200", "150-200万"),
    ("200-250", "200-250万"),
    ("250-350", "250-350万"),
    ("350-*", "350万及以上"),
]

ROOM_FILTERS = [
    ("1", "一室"),
    ("2", "两室"),
    ("3", "三室"),
    ("4", "四室"),
    ("5", "五室及以上"),
]

BUILT_AREA_FILTERS = [
    ("0-60", "60㎡以下"),
    ("60-80", "60-80㎡"),
    ("80-110", "80-110㎡"),
    ("110-150", "110-150㎡"),
    ("150-200", "150-200㎡"),
    ("200-*", "200㎡及以上"),
]

HOUSEZX_MAP = {
    "1": "豪装",
    "2": "精装",
    "3": "中装",
    "4": "简装",
    "5": "清水",
    "6": "毛坯",
}


class DaojialeCrawler:
    def __init__(self, delay: float = 1.0, timeout: int = 30, retries: int = 2):
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://m.daojiale.com/cq/ershoufang",
                "Connection": "keep-alive",
            }
        )

    def page_url(self, page: int, area_id: str = "", filter_param: str = "", filter_value: str = "") -> str:
        params = {"pageNo": str(page)}
        if area_id:
            params["areaId"] = area_id
        if filter_param and filter_value:
            params[filter_param] = filter_value
        return f"{BASE_URL}?{urlencode(params)}"

    def fetch_json(self, url: str) -> Tuple[Optional[dict], str]:
        last_error = ""
        for attempt in range(1, self.retries + 2):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                text = response.text
                if is_blocked(text, response.url):
                    return None, "blocked_or_verification"
                return response.json(), "ok"
            except (requests.RequestException, ValueError) as exc:
                last_error = f"request_error:{exc}"
                if attempt <= self.retries:
                    time.sleep(min(self.delay * attempt, 8))
        return None, last_error

    def crawl_task(
        self,
        rows: List[dict],
        logs: List[dict],
        start_page: int,
        max_pages: int,
        target_count: Optional[int],
        max_empty_pages: int,
        area_id: str = "",
        district_name: str = "",
        filter_type: str = "base",
        filter_name: str = "不限",
        filter_param: str = "",
        filter_value: str = "",
        stop_after_new: Optional[int] = None,
    ) -> Tuple[List[dict], List[dict]]:
        seen = {row.get("dedup_key", "") for row in rows if row.get("dedup_key")}
        empty_pages = 0
        task_new = 0

        for page in range(start_page, start_page + max_pages):
            if target_count and len(rows) >= target_count:
                break
            if stop_after_new and task_new >= stop_after_new:
                break

            url = self.page_url(page, area_id, filter_param, filter_value)
            crawl_time = datetime.now().isoformat(timespec="seconds")
            payload, status = self.fetch_json(url)
            new_count = 0

            if payload and status == "ok":
                data = payload.get("data") or {}
                api_rows = data.get("rows") or []
                for item in api_rows:
                    row = parse_item(item, district_name=district_name, page=page, crawl_time=crawl_time)
                    key = row["dedup_key"]
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(row)
                    new_count += 1
                    task_new += 1
                    if target_count and len(rows) >= target_count:
                        break
                    if stop_after_new and task_new >= stop_after_new:
                        break

            empty_pages = empty_pages + 1 if new_count == 0 else 0
            logs.append(log_row(crawl_time, area_id, district_name, filter_type, filter_name, page, url, status, new_count))
            print(
                f"[{crawl_time}] areaId={area_id or 'all'} district={district_name or 'all'} "
                f"filter={filter_name} page={page} status={status} new={new_count} total={len(rows)}",
                flush=True,
            )

            if empty_pages >= max_empty_pages:
                break
            time.sleep(self.delay)

        return rows, logs


def parse_item(item: Dict, district_name: str, page: int, crawl_time: str) -> dict:
    source_listing_id = str(item.get("houseid") or "")
    title = clean_text(str(item.get("housetitle") or item.get("housetitleOld") or ""))
    district = normalize_district(district_name or str(item.get("areaname") or ""))
    room = normalize_int(item.get("fang"))
    hall = normalize_int(item.get("ting"))
    wei = normalize_int(item.get("wei"))
    layout = build_layout(room, hall, wei)
    area = normalize_number(item.get("builtarea1") or item.get("builtarea"))
    total_price = normalize_number(item.get("saletotalstr") or item.get("saletotal"))
    unit_price = normalize_number(item.get("saleprice"))
    orientation = clean_text(str(item.get("housecx") or ""))
    community = clean_text(str(item.get("buildname") or item.get("community") or ""))
    tags = build_tags(item)
    cover = clean_text(str(item.get("listUrl") or item.get("picUrl") or ""))
    if cover and not cover.endswith(".280x210.jpg"):
        cover = cover + ".280x210.jpg"
    dedup_key = make_dedup_key("daojiale_mobile", source_listing_id, title, area, total_price)

    return {
        "source": "daojiale_mobile",
        "city": "重庆",
        "district": district,
        "page": str(page),
        "source_listing_id": source_listing_id,
        "title": title,
        "area_m2": area,
        "layout": layout,
        "room_count": room,
        "hall_count": hall,
        "orientation": orientation,
        "community": community,
        "tags": tags,
        "total_price_wan": total_price,
        "unit_price_yuan_m2": unit_price,
        "cover_image_url": cover,
        "is_new": "0",
        "crawl_time": crawl_time,
        "dedup_key": dedup_key,
    }


def build_tags(item: Dict) -> str:
    tags = []
    for key in ("housebq", "housebqStr"):
        value = clean_text(str(item.get(key) or ""))
        if value and value != "null":
            tags.extend(re_split_tags(value))
    zx = HOUSEZX_MAP.get(str(item.get("housezx") or ""), "")
    if zx:
        tags.append(zx)
    if str(item.get("isPanorama") or "") == "1":
        tags.append("VR真房源")
    if str(item.get("hasVideo") or "") == "1":
        tags.append("视频房源")
    seen = set()
    result = []
    for tag in tags:
        tag = clean_text(tag)
        if tag.isdigit():
            continue
        if tag and tag not in seen:
            seen.add(tag)
            result.append(tag)
    return "|".join(result)


def re_split_tags(value: str) -> List[str]:
    import re

    return [part.strip() for part in re.split(r"[|,，/、\s]+", value) if part.strip()]


def build_layout(room: str, hall: str, wei: str) -> str:
    parts = []
    if room:
        parts.append(f"{room}室")
    if hall:
        parts.append(f"{hall}厅")
    if wei:
        parts.append(f"{wei}卫")
    return "".join(parts)


def normalize_district(value: str) -> str:
    value = clean_text(value)
    if value != "两江新区":
        value = value.removesuffix("区").removesuffix("县")
    aliases = {"江北": "两江新区", "渝北": "两江新区"}
    return aliases.get(value, value)


def normalize_int(value) -> str:
    text = clean_text(str(value or ""))
    if not text:
        return ""
    try:
        return str(int(float(text)))
    except ValueError:
        return ""


def normalize_number(value) -> str:
    text = clean_text(str(value or ""))
    if not text:
        return ""
    import re

    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return ""
    number = match.group(0)
    return number.rstrip("0").rstrip(".") if "." in number else number


def clean_text(value: str) -> str:
    import re

    value = "" if value is None else str(value)
    value = value.replace("\ufeff", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def make_dedup_key(*parts: str) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def is_blocked(text: str, url: str) -> bool:
    lowered = (text[:5000] + url).lower()
    signals = ["captcha", "verifycode", "访问验证", "安全验证", "验证码", "很抱歉，您访问的页面"]
    return any(signal in lowered for signal in signals)


def log_row(
    crawl_time: str,
    area_id: str,
    district: str,
    filter_type: str,
    filter_name: str,
    page: int,
    url: str,
    status: str,
    count: int,
) -> dict:
    return {
        "crawl_time": crawl_time,
        "area_id": area_id,
        "district": district,
        "filter_type": filter_type,
        "filter_name": filter_name,
        "page": page,
        "url": url,
        "status": status,
        "new_count": count,
    }


def write_csv(path: str, rows: List[dict], fields: List[str]) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return str(output)
    except PermissionError:
        fallback = output.with_name(f"{output.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{output.suffix}")
        with fallback.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        print(f"WARNING: {output} is locked. Wrote CSV to {fallback} instead.", file=sys.stderr)
        return str(fallback)


def write_jsonl(path: str, rows: List[dict]) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("w", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")
        return str(output)
    except PermissionError:
        fallback = output.with_name(f"{output.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{output.suffix}")
        with fallback.open("w", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"WARNING: {output} is locked. Wrote JSONL to {fallback} instead.", file=sys.stderr)
        return str(fallback)


def read_existing_csv(path: str) -> List[dict]:
    input_path = Path(path)
    if not input_path.exists():
        return []
    with input_path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def read_resume_pages(log_path: str) -> dict:
    input_path = Path(log_path)
    if not input_path.exists():
        return {}
    resume_pages = {}
    with input_path.open("r", newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            key = (row.get("area_id", ""), row.get("filter_type", ""), row.get("filter_name", ""))
            page_text = row.get("page", "")
            if not page_text.isdigit():
                continue
            resume_pages[key] = max(resume_pages.get(key, 0), int(page_text) + 1)
    return resume_pages


def build_filter_tasks(expand_filters: bool) -> List[Tuple[str, str, str, str]]:
    tasks = [("base", "不限", "", "")]
    if expand_filters:
        tasks.extend(("price", name, "saletotal", value) for value, name in PRICE_FILTERS)
        tasks.extend(("room", name, "fang", value) for value, name in ROOM_FILTERS)
        tasks.extend(("area", name, "builtArea", value) for value, name in BUILT_AREA_FILTERS)
    return tasks


def selected_area_tasks(args: argparse.Namespace) -> List[Tuple[str, str]]:
    if args.area_id:
        return [(area_id, dict(AREA_FILTERS).get(area_id, "")) for area_id in args.area_id]
    if args.district:
        tasks = []
        for district in args.district:
            for area_id in DISTRICT_TO_AREA_IDS[district]:
                tasks.append((area_id, district))
        return tasks
    if args.by_district:
        return list(AREA_FILTERS)
    return [("", "")]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl Chongqing Daojiale second-hand listing API.")
    parser.add_argument("--start-page", type=int, default=1, help="First page to crawl.")
    parser.add_argument("--max-pages", type=int, default=30, help="Maximum pages per task.")
    parser.add_argument("--target-count", type=int, default=None, help="Stop after collecting this many unique listings.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds.")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds.")
    parser.add_argument("--retries", type=int, default=2, help="HTTP retry count.")
    parser.add_argument("--max-empty-pages", type=int, default=3, help="Stop a task after this many empty pages.")
    parser.add_argument("--by-district", action="store_true", help="Crawl all Daojiale district area IDs.")
    parser.add_argument("--district", action="append", choices=sorted(DISTRICT_TO_AREA_IDS), help="Crawl one district. Can repeat.")
    parser.add_argument("--area-id", action="append", choices=sorted(dict(AREA_FILTERS)), help="Crawl one Daojiale areaId. Can repeat.")
    parser.add_argument("--expand-filters", action="store_true", help="Also crawl price, room, and area filters for every area task.")
    parser.add_argument("--per-filter-count", type=int, default=None, help="Collect at most this many new rows per filter task.")
    parser.add_argument("--append-existing", action="store_true", help="Read existing output CSV first and append new unique rows.")
    parser.add_argument("--resume-from-log", action="store_true", help="Resume every area/filter task from last logged page + 1.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="CSV output path.")
    parser.add_argument("--jsonl", default=DEFAULT_JSONL, help="JSONL output path.")
    parser.add_argument("--log", default=DEFAULT_LOG, help="Crawl log CSV path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    crawler = DaojialeCrawler(delay=args.delay, timeout=args.timeout, retries=args.retries)
    rows = read_existing_csv(args.output) if args.append_existing else []
    if rows:
        print(f"Loaded {len(rows)} existing listings from {args.output}", flush=True)
    resume_pages = read_resume_pages(args.log) if args.resume_from_log else {}
    if resume_pages:
        print(f"Loaded resume pages for {len(resume_pages)} tasks from {args.log}", flush=True)

    logs = []
    try:
        for area_id, district_name in selected_area_tasks(args):
            if args.target_count and len(rows) >= args.target_count:
                break
            for filter_type, filter_name, filter_param, filter_value in build_filter_tasks(args.expand_filters):
                if args.target_count and len(rows) >= args.target_count:
                    break
                start_page = resume_pages.get((area_id, filter_type, filter_name), args.start_page)
                rows, logs = crawler.crawl_task(
                    rows=rows,
                    logs=logs,
                    start_page=start_page,
                    max_pages=args.max_pages,
                    target_count=args.target_count,
                    max_empty_pages=args.max_empty_pages,
                    area_id=area_id,
                    district_name=district_name,
                    filter_type=filter_type,
                    filter_name=filter_name,
                    filter_param=filter_param,
                    filter_value=filter_value,
                    stop_after_new=args.per_filter_count,
                )
    except KeyboardInterrupt:
        print("\nInterrupted by user. Saving collected listings before exit...", file=sys.stderr)

    data_output = write_csv(args.output, rows, FIELDNAMES)
    jsonl_output = write_jsonl(args.jsonl, rows)
    log_output = write_csv(
        args.log,
        logs,
        ["crawl_time", "area_id", "district", "filter_type", "filter_name", "page", "url", "status", "new_count"],
    )
    print(f"Saved {len(rows)} listings to {data_output}")
    print(f"Saved JSONL to {jsonl_output}")
    print(f"Saved crawl log to {log_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
