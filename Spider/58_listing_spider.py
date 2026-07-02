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


BASE_URL = "https://m.58.com/cq/ershoufang/"
DEFAULT_OUTPUT = "data/raw/chongqing_58_listings.csv"
DEFAULT_JSONL = "data/raw/chongqing_58_listings.jsonl"
DEFAULT_LOG = "data/raw/58_crawl_log.csv"

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
    ("changshou", "长寿"),
    ("fuling", "涪陵"),
    ("qijiang", "綦江"),
    ("yongchuan", "永川"),
    ("rongchang", "荣昌"),
    ("tongliang", "铜梁"),
    ("dazu", "大足"),
    ("tongnan", "潼南"),
    ("nanchuan", "南川"),
    ("wanzhou", "万州"),
    ("kaixian", "开州"),
    ("liangping", "梁平"),
    ("wulong", "武隆"),
    ("chengkou", "城口"),
    ("fengdu", "丰都"),
    ("dianjiang", "垫江"),
    ("zhongxian", "忠县"),
    ("yunyang", "云阳"),
    ("fengjie", "奉节"),
    ("wushan", "巫山"),
    ("wuxi", "巫溪"),
    ("shizhu", "石柱"),
    ("xiushan", "秀山"),
    ("youyang", "酉阳"),
    ("pengshui", "彭水"),
    ("qianjiang", "黔江"),
]

AREA_ROUTE_TO_DISTRICT = dict(AREA_TASKS)
DISTRICT_TO_ROUTES = {}
for route, district in AREA_TASKS:
    DISTRICT_TO_ROUTES.setdefault(district, []).append(route)


class WubaListingCrawler:
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

    def page_url(self, area_route: str, page: int) -> str:
        parts = []
        if area_route:
            parts.append(area_route)
        if page > 1:
            parts.append(f"pn{page}")
        path = "/".join(parts)
        return urljoin(BASE_URL, f"{path}/") if path else BASE_URL

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
        start_page: int,
        max_pages: int,
        target_count: Optional[int],
        max_empty_pages: int,
    ) -> Tuple[List[dict], List[dict]]:
        seen = {row.get("dedup_key", "") for row in rows if row.get("dedup_key")}
        empty_pages = 0

        for page in range(start_page, start_page + max_pages):
            if target_count and len(rows) >= target_count:
                break

            url = self.page_url(area_route, page)
            crawl_time = datetime.now().isoformat(timespec="seconds")
            text, status = self.fetch(url)
            new_count = 0

            if text and status == "ok":
                listings = parse_listings(text, district, page, crawl_time)
                for item in listings:
                    key = item["dedup_key"]
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(item)
                    new_count += 1
                    if target_count and len(rows) >= target_count:
                        break

            empty_pages = empty_pages + 1 if new_count == 0 else 0
            logs.append(log_row(crawl_time, area_route, district, page, url, status, new_count))
            print(
                f"[{crawl_time}] route={area_route or 'all'} district={district} page={page} "
                f"status={status} new={new_count} total={len(rows)}",
                flush=True,
            )

            if empty_pages >= max_empty_pages:
                break
            time.sleep(self.delay)

        return rows, logs


def parse_listings(text: str, district: str, page: int, crawl_time: str) -> List[dict]:
    items = []
    blocks = re.findall(r'<li\b(?=[^>]*class=["\'][^"\']*\bitem-wrap\b)[^>]*>.*?</li>', text, flags=re.I | re.S)
    for block in blocks:
        href = extract_first(r'href=["\'](?P<value>https?://m\.58\.com/cq/ershoufang/[^"\']+?\.shtml[^"\']*)["\']', block)
        title = clean_text(extract_first(r'<span[^>]*class=["\'][^"\']*\bcontent-title\b[^"\']*["\'][^>]*>(?P<value>.*?)</span>', block))
        if not href or not title:
            continue

        descs = [
            clean_text(value)
            for value in re.findall(r'<span[^>]*class=["\'][^"\']*\bcontent-desc\b[^"\']*["\'][^>]*>(.*?)</span>', block, flags=re.I | re.S)
        ]
        descs = [value for value in descs if value]
        layout = next((value for value in descs if "室" in value and "厅" in value), "")
        area = normalize_number(next((value for value in descs if "㎡" in value or "m²" in value), ""))
        orientation = next((value for value in descs if value in {"东", "南", "西", "北", "东南", "东北", "西南", "西北", "南北", "东西"}), "")
        image_alt = clean_text(extract_first(r'<img[^>]+alt=["\'](?P<value>[^"\']+)["\']', block))
        community = parse_community(title, descs, image_alt)
        room_count, hall_count = parse_layout(layout)
        total_price = normalize_number(clean_text(extract_first(r'<span[^>]*class=["\'][^"\']*\bcontent-price\b[^"\']*["\'][^>]*>(?P<value>.*?)</span>', block)))
        unit_price = normalize_number(clean_text(extract_first(r'<span[^>]*class=["\'][^"\']*\bhouse-avg-price\b[^"\']*["\'][^>]*>(?P<value>.*?)</span>', block)))
        tags = parse_tags(block)
        cover_image_url = normalize_url(extract_first(r'<img[^>]+src=["\'](?P<value>[^"\']+)["\']', block))
        source_listing_id = extract_source_listing_id(href)
        is_new = "1" if "新上" in tags or "新上" in title else ""
        dedup_key = make_dedup_key("58_mobile", source_listing_id, title, area, total_price)

        items.append(
            {
                "source": "58_mobile",
                "city": "重庆",
                "district": district,
                "filter_type": "base",
                "filter_name": "不限",
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
        )
    return items


def parse_community(title: str, descs: List[str], image_alt: str = "") -> str:
    if image_alt:
        alt = image_alt.replace("二手房图片", "").strip()
        match = re.search(r"^(.+?)(?:\d+\s*室\s*\d*\s*厅|\d+(?:\.\d+)?\s*(?:㎡|m²)|\d+(?:\.\d+)?\s*万)", alt)
        if match:
            return match.group(1).strip()

    if len(descs) >= 5:
        district_or_area = descs[3]
        business = descs[4]
        if district_or_area and business and business in title:
            before = title.split(business, 1)[0].strip()
            return before.replace(district_or_area, "", 1).strip()
    match = re.search(r"(?:区|县|新区)\s+(.+?)\s+(?:一房|二房|三房|四房|五房|六房|\d+室|[一二三四五六七八九十]+室)", title)
    if match:
        return match.group(1).strip()

    match = re.search(r"^([\u4e00-\u9fa5A-Za-z0-9·（）()]{2,24}?)(?:\s|，|,|。|！|!|精装|毛坯|中间楼层|交通|产权|电梯|南向|北向|急售|住家|小三房|轻轨|带)", title)
    return match.group(1).strip() if match else ""


def parse_tags(block: str) -> str:
    tags = [
        clean_text(value)
        for value in re.findall(r'<span[^>]*class=["\'][^"\']*\bhighlight-tag\b[^"\']*["\'][^>]*>(.*?)</span>', block, flags=re.I | re.S)
    ]
    return "|".join(value for value in tags if value)


def parse_layout(layout: str) -> Tuple[str, str]:
    room = extract_layout_number(r"(\d+)\s*室", layout)
    hall = extract_layout_number(r"(\d+)\s*厅", layout)
    return room, hall


def extract_source_listing_id(href: str) -> str:
    match = re.search(r"/ershoufang/(\d+)x?\.shtml", href)
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
    signals = [
        "captcha",
        "callback.58.com/antibot",
        "verifycode",
        "xxzlgatewayurl",
        "访问验证",
        "安全验证",
        "验证码",
        "滑块验证",
    ]
    return any(signal in lowered for signal in signals)


def log_row(crawl_time: str, area_route: str, district: str, page: int, url: str, status: str, count: int) -> dict:
    return {
        "crawl_time": crawl_time,
        "area_route": area_route,
        "district": district,
        "filter_type": "base",
        "filter_name": "不限",
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
            page_text = row.get("page", "")
            if not page_text.isdigit():
                continue
            resume_pages[route] = max(resume_pages.get(route, 0), int(page_text) + 1)
    return resume_pages


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
    parser = argparse.ArgumentParser(description="Crawl Chongqing 58 mobile second-hand listing pages.")
    parser.add_argument("--start-page", type=int, default=1, help="First page to crawl.")
    parser.add_argument("--max-pages", type=int, default=20, help="Maximum pages to crawl per route.")
    parser.add_argument("--target-count", type=int, default=None, help="Stop after collecting this many unique listings.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds.")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds.")
    parser.add_argument("--retries", type=int, default=2, help="HTTP retry count.")
    parser.add_argument("--max-empty-pages", type=int, default=5, help="Stop a route after this many empty pages.")
    parser.add_argument("--by-district", action="store_true", help="Crawl all mapped district routes.")
    parser.add_argument("--district", action="append", choices=sorted(DISTRICT_TO_ROUTES), help="Crawl one output district. Can repeat.")
    parser.add_argument("--area-route", action="append", choices=sorted(AREA_ROUTE_TO_DISTRICT), help="Crawl one 58 route. Can repeat.")
    parser.add_argument("--append-existing", action="store_true", help="Read existing output CSV first and append new unique rows.")
    parser.add_argument("--resume-from-log", action="store_true", help="Resume every route from last logged page + 1.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="CSV output path.")
    parser.add_argument("--jsonl", default=DEFAULT_JSONL, help="JSONL output path.")
    parser.add_argument("--log", default=DEFAULT_LOG, help="Crawl log CSV path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    crawler = WubaListingCrawler(delay=args.delay, timeout=args.timeout, retries=args.retries)
    rows = read_existing_csv(args.output) if args.append_existing else []
    if rows:
        print(f"Loaded {len(rows)} existing listings from {args.output}", flush=True)
    resume_pages = read_resume_pages(args.log) if args.resume_from_log else {}
    if resume_pages:
        print(f"Loaded resume pages for {len(resume_pages)} routes from {args.log}", flush=True)

    logs = []
    try:
        for area_route, district in selected_area_tasks(args):
            if args.target_count and len(rows) >= args.target_count:
                break
            start_page = resume_pages.get(area_route, args.start_page)
            rows, logs = crawler.crawl_task(
                rows=rows,
                logs=logs,
                area_route=area_route,
                district=district,
                start_page=start_page,
                max_pages=args.max_pages,
                target_count=args.target_count,
                max_empty_pages=args.max_empty_pages,
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
