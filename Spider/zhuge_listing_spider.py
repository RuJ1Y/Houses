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


BASE_URL = "https://m.zhuge.com/cq/ershoufang/"
DEFAULT_OUTPUT = "data/raw/chongqing_zhuge_listings.csv"
DEFAULT_JSONL = "data/raw/chongqing_zhuge_listings.jsonl"
DEFAULT_LOG = "data/raw/zhuge_crawl_log.csv"

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

# The first value is the Zhuge route segment. The second value is the district
# name written into the CSV. Per request, Yubei and Jiangbei are merged into
# Liangjiang New Area.
AREA_TASKS = [
    ("yubei", "两江新区"),
    ("jiangbei", "两江新区"),
    ("nanan", "南岸"),
    ("jiulongpo", "九龙坡"),
    ("shapingba", "沙坪坝"),
    ("yuzhong", "渝中"),
    ("banan", "巴南"),
    ("dadukou", "大渡口"),
    ("beibei", "北碚"),
    ("bishan", "璧山"),
    ("jiangjin", "江津"),
    ("hechuan", "合川"),
    ("fuling", "长寿"),
    ("qijiang", "綦江"),
    ("yongchuan", "永川"),
    ("rongchang", "荣昌"),
    ("tongliang", "铜梁"),
    ("dazu", "大足"),
    ("tongnan", "潼南"),
    ("nanchuan", "南川"),
    ("shuangqiao", "大足"),
    ("wansheng", "綦江"),
    ("fuling1", "涪陵"),
    ("chengkou", "城口"),
    ("dianjiang", "垫江"),
    ("fengdu", "丰都"),
    ("fengjie", "奉节"),
    ("liangping", "梁平"),
    ("wuxi", "巫溪"),
    ("wushan", "巫山"),
    ("wanzhou", "万州"),
    ("yunyang", "云阳"),
    ("zhongxian", "忠县"),
    ("kaizhou", "开州"),
    ("pengshui", "彭水"),
    ("wulong", "武隆"),
    ("qianjiang", "黔江"),
    ("shizhu", "石柱"),
    ("xiushan", "秀山"),
    ("youyang", "酉阳"),
]

AREA_ROUTE_TO_DISTRICT = dict(AREA_TASKS)
DISTRICT_TO_ROUTES = {}
for route, district in AREA_TASKS:
    DISTRICT_TO_ROUTES.setdefault(district, []).append(route)

BASE_FILTER = ("base", "不限", "")
NEW_FILTER = ("tag", "新上房源", "t2")
PRICE_FILTERS = [
    ("price", "100万以下", "jiage-100"),
    ("price", "100-200万", "jiage100-200"),
    ("price", "200-300万", "jiage200-300"),
    ("price", "300-500万", "jiage300-500"),
    ("price", "500-1000万", "jiage500-1000"),
    ("price", "1000万以上", "jiage1000"),
]


class ZhugeListingCrawler:
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

    def page_url(self, area_route: str, page: int, filter_route: str = "") -> str:
        parts = [area_route]
        if filter_route:
            parts.append(filter_route)
        if page > 1:
            parts.append(f"p{page}")
        path = "/".join(part.strip("/") for part in parts if part)
        return urljoin(BASE_URL, f"{path}/")

    def fetch(self, url: str) -> Tuple[Optional[str], str]:
        last_error = ""
        for attempt in range(1, self.retries + 2):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                response.encoding = response.apparent_encoding or "utf-8"
                text = response.text
                if is_blocked(text, response.url):
                    return None, "blocked_or_verification"
                return text, "ok"
            except requests.RequestException as exc:
                last_error = f"request_error:{exc}"
                if attempt <= self.retries:
                    time.sleep(min(self.delay * attempt, 8))
        return None, last_error

    def crawl_task(
        self,
        rows: List[dict],
        logs: List[dict],
        area_route: str,
        district: str,
        filter_type: str,
        filter_name: str,
        filter_route: str,
        start_page: int,
        max_pages: int,
        target_count: Optional[int],
        max_empty_pages: int,
        stop_after_new: Optional[int],
    ) -> Tuple[List[dict], List[dict]]:
        seen = {row.get("dedup_key", "") for row in rows if row.get("dedup_key")}
        empty_pages = 0
        task_new = 0

        for page in range(start_page, start_page + max_pages):
            if target_count and len(rows) >= target_count:
                break
            if stop_after_new and task_new >= stop_after_new:
                break

            url = self.page_url(area_route, page, filter_route)
            crawl_time = datetime.now().isoformat(timespec="seconds")
            text, status = self.fetch(url)
            new_count = 0

            if text and status == "ok":
                listings = parse_listings(
                    text=text,
                    district=district,
                    page=page,
                    crawl_time=crawl_time,
                    filter_type=filter_type,
                    filter_name=filter_name,
                )
                for item in listings:
                    key = item["dedup_key"]
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(item)
                    new_count += 1
                    task_new += 1
                    if target_count and len(rows) >= target_count:
                        break
                    if stop_after_new and task_new >= stop_after_new:
                        break

            if new_count == 0:
                empty_pages += 1
            else:
                empty_pages = 0

            logs.append(log_row(crawl_time, area_route, district, filter_type, filter_name, page, url, status, new_count))
            print(
                f"[{crawl_time}] route={area_route} district={district} "
                f"filter={filter_name} page={page} new={new_count} total={len(rows)}",
                flush=True,
            )

            if empty_pages >= max_empty_pages:
                break
            time.sleep(self.delay)

        return rows, logs


def parse_listings(
    text: str,
    district: str,
    page: int,
    crawl_time: str,
    filter_type: str,
    filter_name: str,
) -> List[dict]:
    items = []
    for match in re.finditer(r'<a\b(?=[^>]*class=["\'][^"\']*\blist-item\b)[^>]*>.*?</a>', text, flags=re.I | re.S):
        block = match.group(0)
        href = extract_first(r'href=["\'](?P<value>[^"\']+)["\']', block)
        title = clean_text(extract_first(r"<b[^>]*>(?P<value>.*?)</b>", block))
        if not href or not title:
            continue

        source_listing_id = extract_source_listing_id(href)
        sumy = clean_text(extract_first(r'<span[^>]*class=["\'][^"\']*\bsumy-list\b[^"\']*["\'][^>]*>(?P<value>.*?)</span>', block))
        area, layout, community = parse_summary(sumy)
        room_count, hall_count = parse_layout(layout)
        tags = parse_tags(block)
        total_price = normalize_number(clean_text(extract_first(r'<span[^>]*class=["\'][^"\']*\bprice-title\b[^"\']*["\'][^>]*>(?P<value>.*?)</span>', block)))
        unit_price = normalize_number(clean_text(extract_first(r'<span[^>]*class=["\'][^"\']*\bavg-price\b[^"\']*["\'][^>]*>(?P<value>.*?)</span>', block)))
        cover_image_url = normalize_url(
            extract_first(r'data-src=["\'](?P<value>[^"\']+)["\']', block)
            or extract_first(r'<img[^>]+src=["\'](?P<value>[^"\']+)["\']', block)
        )
        is_new = "1" if filter_name == "新上房源" or "新上" in tags else ""
        dedup_key = make_dedup_key("zhuge_mobile", source_listing_id, title, area, total_price)

        items.append(
            {
                "source": "zhuge_mobile",
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
                "orientation": "",
                "community": community,
                "tags": tags,
                "total_price_wan": total_price,
                "unit_price_yuan_m2": unit_price,
                "cover_image_url": cover_image_url,
                "is_new": is_new,
                "crawl_time": crawl_time,
                "dedup_key": dedup_key,
            }
        )
    return items


def parse_summary(value: str) -> Tuple[str, str, str]:
    parts = [part.strip() for part in value.split("|")]
    area = normalize_number(parts[0]) if len(parts) >= 1 else ""
    layout = parts[1] if len(parts) >= 2 else ""
    community = parts[2] if len(parts) >= 3 else ""
    return area, layout, community


def parse_layout(layout: str) -> Tuple[str, str]:
    room = extract_layout_number(r"(\d+)\s*室", layout)
    hall = extract_layout_number(r"(\d+)\s*厅", layout)
    return room, hall


def parse_tags(block: str) -> str:
    tag_block = extract_first(r'<span[^>]*class=["\'][^"\']*\btag-box\b[^"\']*["\'][^>]*>(?P<value>.*?)</span>\s*</span>', block)
    if not tag_block:
        tag_block = extract_first(r'<span[^>]*class=["\'][^"\']*\btag-box\b[^"\']*["\'][^>]*>(?P<value>.*?)</span>', block)
    tags = []
    for tag in re.findall(r"<span[^>]*>(.*?)</span>", tag_block, flags=re.I | re.S):
        value = clean_text(tag)
        if value:
            tags.append(value)
    return "|".join(tags)


def extract_source_listing_id(href: str) -> str:
    match = re.search(r"/ershoufang/(\d+)/(\d+)\.html", href)
    if match:
        return match.group(2)
    match = re.search(r"(\d+)\.html", href)
    return match.group(1) if match else ""


def extract_first(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.I | re.S)
    if not match:
        return ""
    return html.unescape(match.group("value")).strip()


def extract_layout_number(pattern: str, value: str) -> str:
    match = re.search(pattern, value)
    return match.group(1) if match else ""


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_number(value: str) -> str:
    match = re.search(r"\d+(?:\.\d+)?", value)
    return match.group(0) if match else ""


def normalize_url(value: str) -> str:
    if value.startswith("//"):
        return "https:" + value
    return value


def make_dedup_key(*parts: str) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def is_blocked(text: str, url: str) -> bool:
    lowered = (text[:5000] + url).lower()
    signals = ["captcha", "访问验证", "安全验证", "验证码", "滑块验证"]
    return any(signal in lowered for signal in signals)


def log_row(
    crawl_time: str,
    area_route: str,
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
        "area_route": area_route,
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
            route = row.get("area_route", "")
            filter_type = row.get("filter_type", "")
            filter_name = row.get("filter_name", "")
            page_text = row.get("page", "")
            if not route or not page_text.isdigit():
                continue
            key = (route, filter_type, filter_name)
            resume_pages[key] = max(resume_pages.get(key, 0), int(page_text) + 1)
    return resume_pages


def build_filter_tasks(expand_filters: bool) -> List[Tuple[str, str, str]]:
    tasks = [BASE_FILTER]
    if expand_filters:
        tasks.append(NEW_FILTER)
        tasks.extend(PRICE_FILTERS)
    return tasks


def selected_area_tasks(args: argparse.Namespace) -> List[Tuple[str, str]]:
    if args.area_route:
        return [(route, AREA_ROUTE_TO_DISTRICT[route]) for route in args.area_route]
    if args.district:
        tasks = []
        for district in args.district:
            for route in DISTRICT_TO_ROUTES[district]:
                tasks.append((route, district))
        return tasks
    if args.by_district:
        return list(AREA_TASKS)
    return [("", "")]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl Chongqing Zhuge mobile second-hand listing pages.")
    parser.add_argument("--start-page", type=int, default=1, help="First page to crawl.")
    parser.add_argument("--max-pages", type=int, default=20, help="Maximum pages to crawl per task.")
    parser.add_argument("--target-count", type=int, default=None, help="Stop after collecting this many unique listings.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds.")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds.")
    parser.add_argument("--retries", type=int, default=2, help="HTTP retry count.")
    parser.add_argument("--max-empty-pages", type=int, default=5, help="Stop a task after this many empty pages.")
    parser.add_argument("--by-district", action="store_true", help="Crawl all mapped district routes.")
    parser.add_argument("--district", action="append", choices=sorted(DISTRICT_TO_ROUTES), help="Crawl one output district. Can repeat.")
    parser.add_argument("--area-route", action="append", choices=sorted(AREA_ROUTE_TO_DISTRICT), help="Crawl one Zhuge route. Can repeat.")
    parser.add_argument("--expand-filters", action="store_true", help="Also crawl new-listing and verified price filter routes.")
    parser.add_argument("--per-filter-count", type=int, default=None, help="Collect at most this many new rows per route/filter task.")
    parser.add_argument("--append-existing", action="store_true", help="Read existing output CSV first and append new unique rows.")
    parser.add_argument("--resume-from-log", action="store_true", help="Resume every route/filter from last logged page + 1.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="CSV output path.")
    parser.add_argument("--jsonl", default=DEFAULT_JSONL, help="JSONL output path.")
    parser.add_argument("--log", default=DEFAULT_LOG, help="Crawl log CSV path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    crawler = ZhugeListingCrawler(delay=args.delay, timeout=args.timeout, retries=args.retries)
    rows = read_existing_csv(args.output) if args.append_existing else []
    if rows:
        print(f"Loaded {len(rows)} existing listings from {args.output}", flush=True)
    resume_pages = read_resume_pages(args.log) if args.resume_from_log else {}
    if resume_pages:
        print(f"Loaded resume pages for {len(resume_pages)} route/filter tasks from {args.log}", flush=True)

    logs = []
    area_tasks = selected_area_tasks(args)
    filter_tasks = build_filter_tasks(args.expand_filters)

    try:
        for area_route, district in area_tasks:
            if args.target_count and len(rows) >= args.target_count:
                break
            for filter_type, filter_name, filter_route in filter_tasks:
                if args.target_count and len(rows) >= args.target_count:
                    break
                start_page = resume_pages.get((area_route, filter_type, filter_name), args.start_page)
                rows, logs = crawler.crawl_task(
                    rows=rows,
                    logs=logs,
                    area_route=area_route,
                    district=district,
                    filter_type=filter_type,
                    filter_name=filter_name,
                    filter_route=filter_route,
                    start_page=start_page,
                    max_pages=args.max_pages,
                    target_count=args.target_count,
                    max_empty_pages=args.max_empty_pages,
                    stop_after_new=args.per_filter_count,
                )
    except KeyboardInterrupt:
        print("\nInterrupted by user. Saving collected listings before exit...", file=sys.stderr)

    data_output = write_csv(args.output, rows, FIELDNAMES)
    jsonl_output = write_jsonl(args.jsonl, rows)
    log_output = write_csv(
        args.log,
        logs,
        ["crawl_time", "area_route", "district", "filter_type", "filter_name", "page", "url", "status", "new_count"],
    )
    print(f"Saved {len(rows)} listings to {data_output}")
    print(f"Saved JSONL to {jsonl_output}")
    print(f"Saved crawl log to {log_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
