import argparse
import csv
import hashlib
import html
import json
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests


BASE_URL = "https://m.fang.com/esf/cq/"
DEFAULT_OUTPUT = "data/raw/chongqing_mobile_fang_listings.csv"
DEFAULT_JSONL = "data/raw/chongqing_mobile_fang_listings.jsonl"
DEFAULT_LOG = "data/raw/mobile_fang_crawl_log.csv"

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
    "filter_type",
    "filter_name",
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

DISTRICT_NAMES = [
    "两江新区",
    "九龙坡",
    "大渡口",
    "沙坪坝",
    "万州",
    "涪陵",
    "渝中",
    "江北",
    "南岸",
    "北碚",
    "渝北",
    "巴南",
    "黔江",
    "长寿",
    "江津",
    "合川",
    "永川",
    "南川",
    "綦江",
    "大足",
    "璧山",
    "铜梁",
    "潼南",
    "荣昌",
    "开州",
    "梁平",
    "武隆",
    "城口",
    "丰都",
    "垫江",
    "忠县",
    "云阳",
    "奉节",
    "巫山",
    "巫溪",
    "石柱",
    "秀山",
    "酉阳",
    "彭水",
]

DISTRICT_CODES = {
    "两江新区": "58",
    "渝中": "56",
    "南岸": "59",
    "沙坪坝": "60",
    "九龙坡": "61",
    "巴南": "64",
    "大渡口": "62",
    "北碚": "63",
    "合川": "11841",
    "涪陵": "11828",
    "江津": "11833",
    "璧山": "11840",
    "永川": "11839",
    "綦江": "11831",
    "长寿": "11825",
    "大足": "11826",
    "垫江": "11827",
    "南川": "11829",
    "彭水": "11830",
    "荣昌": "11832",
    "铜梁": "11834",
    "潼南": "11835",
    "万州": "11837",
    "武隆": "11838",
    "丰都": "16707",
    "奉节": "16708",
    "梁平": "16709",
    "黔江": "16710",
    "石柱": "16711",
    "巫山": "16712",
    "云阳": "16713",
    "忠县": "16714",
    "城口": "16718",
    "巫溪": "16719",
    "开州": "16748",
    "秀山": "17400",
    "酉阳": "17401",
}

PRICE_FILTERS = [
    ("price", "40万以下", "price", "0,40"),
    ("price", "40-60万", "price", "40,60"),
    ("price", "60-80万", "price", "60,80"),
    ("price", "80-100万", "price", "80,100"),
    ("price", "100-120万", "price", "100,120"),
    ("price", "120-150万", "price", "120,150"),
    ("price", "150-200万", "price", "150,200"),
    ("price", "200-300万", "price", "200,300"),
    ("price", "300万以上", "price", "300,0"),
]

ROOM_FILTERS = [
    ("room", "一居", "room", "0"),
    ("room", "二居", "room", "1"),
    ("room", "三居", "room", "2"),
    ("room", "四居", "room", "3"),
    ("room", "五居", "room", "4"),
    ("room", "五居以上", "room", "5"),
]

AREA_FILTERS = [
    ("area", "50㎡以下", "area", "0,50"),
    ("area", "50-70㎡", "area", "50,70"),
    ("area", "70-90㎡", "area", "70,90"),
    ("area", "90-110㎡", "area", "90,110"),
    ("area", "110-130㎡", "area", "110,130"),
    ("area", "130-150㎡", "area", "130,150"),
    ("area", "150-200㎡", "area", "150,200"),
    ("area", "200-300㎡", "area", "200,300"),
    ("area", "300㎡以上", "area", "300,"),
]

BASE_FILTER = ("base", "不限", "", "")


class MobileFangListingCrawler:
    def __init__(self, delay: float = 1.0, timeout: int = 30, retries: int = 2):
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Connection": "keep-alive",
            }
        )

    def page_url(self, page: int, district_code: str = "", filter_param: str = "", filter_value: str = "") -> str:
        url = BASE_URL if page <= 1 else urljoin(BASE_URL, f"{page}/")
        params = []
        if district_code:
            params.append(f"district={district_code}")
        if filter_param:
            params.append(f"{filter_param}={filter_value}")
        return f"{url}?{'&'.join(params)}" if params else url

    def fetch(self, url: str) -> Tuple[Optional[str], str]:
        last_error = ""
        for attempt in range(1, self.retries + 2):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                text = response.content.decode("gb18030", errors="replace")
                if is_blocked(text, response.url):
                    return None, "blocked_or_verification"
                return text, "ok"
            except requests.RequestException as exc:
                last_error = f"request_error:{exc}"
                if attempt <= self.retries:
                    time.sleep(min(self.delay * attempt, 8))
        return None, last_error

    def crawl(
        self,
        start_page: int,
        max_pages: int,
        target_count: Optional[int],
        max_empty_pages: int,
        initial_rows: Optional[List[dict]] = None,
        district_name: str = "",
        district_code: str = "",
        stop_after_new: Optional[int] = None,
        filter_type: str = "",
        filter_name: str = "",
        filter_param: str = "",
        filter_value: str = "",
    ) -> Tuple[List[dict], List[dict]]:
        rows: List[dict] = list(initial_rows or [])
        logs: List[dict] = []
        seen = {row.get("dedup_key", "") for row in rows if row.get("dedup_key")}
        empty_pages = 0
        district_new_total = 0

        end_page = start_page + max_pages - 1
        for page in range(start_page, end_page + 1):
            url = self.page_url(
                page,
                district_code=district_code,
                filter_param=filter_param,
                filter_value=filter_value,
            )
            text, status = self.fetch(url)
            crawl_time = datetime.now().isoformat(timespec="seconds")
            if status != "ok" or not text:
                logs.append(log_row(crawl_time, district_name, filter_type, filter_name, page, url, status, 0))
                print(
                    f"[{crawl_time}] district={district_name or 'ALL'} page={page} "
                    f"filter={filter_name or '不限'} status={status} total={len(rows)}",
                    flush=True,
                )
                if status == "blocked_or_verification":
                    break
                empty_pages += 1
                if empty_pages >= max_empty_pages:
                    break
                continue

            parsed = parse_listings(
                text,
                page,
                url,
                crawl_time,
                district_name=district_name,
                filter_type=filter_type,
                filter_name=filter_name,
            )
            new_count = 0
            for item in parsed:
                key = item["dedup_key"]
                if key in seen:
                    continue
                seen.add(key)
                rows.append(item)
                new_count += 1
                district_new_total += 1
                if stop_after_new and district_new_total >= stop_after_new:
                    break

            logs.append(log_row(crawl_time, district_name, filter_type, filter_name, page, url, "ok", new_count))
            print(
                f"[{crawl_time}] district={district_name or 'ALL'} page={page} "
                f"filter={filter_name or '不限'} new={new_count} total={len(rows)}",
                flush=True,
            )

            if stop_after_new and district_new_total >= stop_after_new:
                break

            if new_count == 0:
                empty_pages += 1
                if empty_pages >= max_empty_pages:
                    break
            else:
                empty_pages = 0

            if target_count and len(rows) >= target_count:
                rows = rows[:target_count]
                break

            time.sleep(self.delay + random.uniform(0, 0.5))

        return rows, logs


def is_blocked(text: str, final_url: str) -> bool:
    haystack = f"{final_url}\n{text[:5000]}".lower()
    markers = [
        "captcha",
        "verifycode",
        "访问验证",
        "请完成验证",
        "antibot",
        "blocked",
    ]
    return any(marker.lower() in haystack for marker in markers)


def parse_listings(
    text: str,
    page: int,
    page_url: str,
    crawl_time: str,
    district_name: str = "",
    filter_type: str = "",
    filter_name: str = "",
) -> List[dict]:
    rows: List[dict] = []
    blocks = re.findall(r'<li class="listhouse"[\s\S]*?</li>', text, flags=re.I)
    for block in blocks:
        item = parse_listing_block(
            block,
            page,
            page_url,
            crawl_time,
            district_name=district_name,
            filter_type=filter_type,
            filter_name=filter_name,
        )
        if item:
            rows.append(item)
    return rows


def parse_listing_block(
    block: str,
    page: int,
    page_url: str,
    crawl_time: str,
    district_name: str = "",
    filter_type: str = "",
    filter_name: str = "",
) -> Optional[dict]:
    source_listing_id = extract_first(r'"houseid"\s*:\s*"?(?P<value>\d+)"?', block)
    if not source_listing_id or source_listing_id == "0":
        href_match = re.search(r'href=["\']//m\.fang\.com/esf/cq/3_(\d+)\.html["\']', block)
        source_listing_id = href_match.group(1) if href_match else ""
    if not source_listing_id or source_listing_id == "0":
        return None

    title = clean_text(extract_first(r"<h3[^>]*>(?P<value>[\s\S]*?)</h3>", block))
    if not title:
        title = clean_text(extract_first(r'alt=["\'](?P<value>[^"\']+)["\']', block))

    cover_image_url = extract_cover_image_url(block)
    district = district_name or infer_district(title)
    is_new = "1" if "新上" in title or 'icon-new' in block else "0"

    spans = [
        clean_text(value)
        for value in re.findall(r"<p>\s*((?:<span>[\s\S]*?</span>)+)\s*</p>", block, flags=re.I)
        for value in re.findall(r"<span>([\s\S]*?)</span>", value, flags=re.I)
    ]
    area = ""
    layout = ""
    orientation = ""
    community = ""
    if len(spans) >= 1:
        area = normalize_number(spans[0].replace("㎡", ""))
    if len(spans) >= 2:
        layout = spans[1]
    if len(spans) >= 3:
        orientation = spans[2]
    if len(spans) >= 4:
        community = spans[3]
    room_count, hall_count = parse_layout(layout)

    tags = ""
    tag_block = extract_first(r'<div class="stag">(?P<value>[\s\S]*?)</div>', block)
    if tag_block:
        tag_values = re.findall(r"<span[^>]*>([\s\S]*?)</span>", tag_block, re.I)
        tags = "|".join(clean_text(tag) for tag in tag_values if clean_text(tag))

    total_price = extract_first(r'<div class="price[^"]*">\s*<span><em>(?P<value>[\d.]+)</em>\s*万', block)
    unit_price = extract_first(r'<span class="del-price">(?P<value>[\d.]+)元/㎡</span>', block)
    if not unit_price:
        unit_price = extract_first(r'(?P<value>\d{3,6})元/㎡', clean_text(block))

    dedup_key = make_dedup_key("mobile_fang", source_listing_id, title, area, total_price)
    return {
        "source": "mobile_fang",
        "city": "重庆",
        "district": district,
        "filter_type": filter_type,
        "filter_name": filter_name,
        "page": page,
        "source_listing_id": source_listing_id,
        "title": title,
        "area_m2": area,
        "layout": layout,
        "room_count": room_count,
        "hall_count": hall_count,
        "orientation": orientation,
        "community": community,
        "tags": tags,
        "total_price_wan": total_price,
        "unit_price_yuan_m2": unit_price,
        "cover_image_url": cover_image_url,
        "is_new": is_new,
        "crawl_time": crawl_time,
        "dedup_key": dedup_key,
    }


def extract_first(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.I | re.S)
    if not match:
        return ""
    return html.unescape(match.group("value")).strip()


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_number(value: str) -> str:
    match = re.search(r"\d+(?:\.\d+)?", value)
    return match.group(0) if match else ""


def parse_layout(layout: str) -> Tuple[str, str]:
    room = extract_layout_number(r"(\d+)\s*室", layout)
    hall = extract_layout_number(r"(\d+)\s*厅", layout)
    return room, hall


def extract_layout_number(pattern: str, value: str) -> str:
    match = re.search(pattern, value)
    return match.group(1) if match else ""


def infer_district(title: str) -> str:
    for district in DISTRICT_NAMES:
        if district in title:
            return district
    return ""


def extract_cover_image_url(block: str) -> str:
    value = extract_first(r'data-original=["\'](?P<value>[^"\']+)["\']', block)
    if not value:
        value = extract_first(r'<img[^>]+src=["\'](?P<value>[^"\']+)["\']', block)
    if value.startswith("//"):
        return "https:" + value
    return value


def make_dedup_key(*parts: str) -> str:
    raw = "|".join(part or "" for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def log_row(
    crawl_time: str,
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
            district = row.get("district", "")
            page_text = row.get("page", "")
            if not district or not page_text.isdigit():
                continue
            page = int(page_text)
            resume_pages[district] = max(resume_pages.get(district, 0), page + 1)
    return resume_pages


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl Chongqing mobile Fang.com second-hand listing pages.")
    parser.add_argument("--start-page", type=int, default=1, help="First page to crawl.")
    parser.add_argument("--max-pages", type=int, default=20, help="Maximum pages to crawl.")
    parser.add_argument("--target-count", type=int, default=None, help="Stop after collecting this many unique listings.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds.")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds.")
    parser.add_argument("--retries", type=int, default=2, help="HTTP retry count.")
    parser.add_argument("--max-empty-pages", type=int, default=5, help="Stop after this many consecutive empty pages.")
    parser.add_argument(
        "--by-district",
        action="store_true",
        help="Crawl every district separately and write district names directly into rows.",
    )
    parser.add_argument(
        "--district",
        action="append",
        choices=sorted(DISTRICT_CODES),
        help="Only crawl the named district. Can be used multiple times. Implies district URL filtering.",
    )
    parser.add_argument(
        "--per-district-count",
        type=int,
        default=None,
        help="When crawling by district, collect at most this many new unique listings per district.",
    )
    parser.add_argument(
        "--expand-filters",
        action="store_true",
        help="For each district, crawl base results plus price/room/area filter tasks.",
    )
    parser.add_argument(
        "--per-filter-count",
        type=int,
        default=None,
        help="When --expand-filters is enabled, collect at most this many new unique listings per filter task.",
    )
    parser.add_argument(
        "--append-existing",
        action="store_true",
        help="Read existing output CSV first, then append new unique listings instead of starting from empty data.",
    )
    parser.add_argument(
        "--resume-from-log",
        action="store_true",
        help="When crawling districts, read the log file and resume each district from its last logged page + 1.",
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="CSV output path.")
    parser.add_argument("--jsonl", default=DEFAULT_JSONL, help="JSONL output path.")
    parser.add_argument("--log", default=DEFAULT_LOG, help="Crawl log CSV path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    crawler = MobileFangListingCrawler(delay=args.delay, timeout=args.timeout, retries=args.retries)
    existing_rows = read_existing_csv(args.output) if args.append_existing else []
    if existing_rows:
        print(f"Loaded {len(existing_rows)} existing listings from {args.output}", flush=True)
    resume_pages = read_resume_pages(args.log) if args.resume_from_log else {}
    if resume_pages:
        print(f"Loaded resume pages for {len(resume_pages)} districts from {args.log}", flush=True)
    rows = list(existing_rows)
    logs = []
    if args.by_district or args.district:
        district_names = args.district or list(DISTRICT_CODES.keys())
        for district_name in district_names:
            if args.target_count and len(rows) >= args.target_count:
                break
            filter_tasks = [BASE_FILTER]
            if args.expand_filters:
                filter_tasks.extend(PRICE_FILTERS)
                filter_tasks.extend(ROOM_FILTERS)
                filter_tasks.extend(AREA_FILTERS)
            district_new_before = len(rows)
            for filter_type, filter_name, filter_param, filter_value in filter_tasks:
                if args.target_count and len(rows) >= args.target_count:
                    break
                if args.per_district_count and len(rows) - district_new_before >= args.per_district_count:
                    break
                stop_after = args.per_filter_count if args.expand_filters else args.per_district_count
                if args.per_district_count:
                    remaining_for_district = args.per_district_count - (len(rows) - district_new_before)
                    stop_after = min(stop_after or remaining_for_district, remaining_for_district)
                remaining_target = args.target_count if args.target_count is None else args.target_count
                district_start_page = resume_pages.get(district_name, args.start_page) if filter_type == "base" else args.start_page
                rows, district_logs = crawler.crawl(
                    start_page=district_start_page,
                    max_pages=args.max_pages,
                    target_count=remaining_target,
                    max_empty_pages=args.max_empty_pages,
                    initial_rows=rows,
                    district_name=district_name,
                    district_code=DISTRICT_CODES[district_name],
                    stop_after_new=stop_after,
                    filter_type=filter_type,
                    filter_name=filter_name,
                    filter_param=filter_param,
                    filter_value=filter_value,
                )
                logs.extend(district_logs)
    else:
        rows, logs = crawler.crawl(
            start_page=args.start_page,
            max_pages=args.max_pages,
            target_count=args.target_count,
            max_empty_pages=args.max_empty_pages,
            initial_rows=rows,
        )
    data_output = write_csv(args.output, rows, FIELDNAMES)
    jsonl_output = write_jsonl(args.jsonl, rows)
    log_output = write_csv(
        args.log,
        logs,
        ["crawl_time", "district", "filter_type", "filter_name", "page", "url", "status", "new_count"],
    )
    print(f"Saved {len(rows)} listings to {data_output}")
    print(f"Saved JSONL to {jsonl_output}")
    print(f"Saved crawl log to {log_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
