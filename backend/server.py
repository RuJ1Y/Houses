from __future__ import annotations

import csv
import json
import math
import mimetypes
import os
import statistics
from collections import Counter, defaultdict
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DATA_FILE = PROJECT_DIR / "Spider" / "data" / "clean" / "chongqing_fang_daojiale_cleaned_dedup.csv"
STATIC_DIR = BASE_DIR / "static"
ALLOWED_IMAGE_HOSTS = ("soufunimg.com", "fangimg.com")


def to_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.lower() == "nan":
            return None
        return float(text)
    except ValueError:
        return None


def to_int(value: str | None) -> int | None:
    number = to_float(value)
    if number is None or math.isnan(number):
        return None
    return int(number)


def parse_listing(row: dict[str, str]) -> dict:
    area = to_float(row.get("area_m2"))
    total_price = to_float(row.get("total_price_wan"))
    unit_price = to_int(row.get("unit_price_yuan_m2"))
    room_count = to_int(row.get("room_count"))
    hall_count = to_int(row.get("hall_count"))
    tags = [tag for tag in (row.get("tags") or "").split("|") if tag]

    return {
        "source": row.get("source") or "",
        "city": row.get("city") or "",
        "district": row.get("district") or "未知",
        "page": to_int(row.get("page")) or 0,
        "sourceListingId": row.get("source_listing_id") or "",
        "title": row.get("title") or "",
        "areaM2": area,
        "layout": row.get("layout") or "",
        "roomCount": room_count,
        "hallCount": hall_count,
        "orientation": row.get("orientation") or "",
        "community": row.get("community") or "",
        "tags": tags,
        "totalPriceWan": total_price,
        "unitPriceYuanM2": unit_price,
        "coverImageUrl": row.get("cover_image_url") or "",
        "isNew": (to_int(row.get("is_new")) or 0) == 1,
        "crawlTime": row.get("crawl_time") or "",
        "dedupKey": row.get("dedup_key") or "",
    }


def load_listings() -> list[dict]:
    if not DATA_FILE.exists():
        return []
    with DATA_FILE.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return [parse_listing(row) for row in reader]


LISTINGS = load_listings()
VALID_LISTINGS = [
    item
    for item in LISTINGS
    if item["areaM2"] is not None
    and item["totalPriceWan"] is not None
    and item["unitPriceYuanM2"] is not None
]


def avg(values: list[float | int]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def median(values: list[float | int]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return statistics.median(clean)


def percentile(values: list[float | int], ratio: float) -> float | None:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * ratio
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return clean[lower]
    weight = position - lower
    return clean[lower] * (1 - weight) + clean[upper] * weight


def round_or_none(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def group_by_district() -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in VALID_LISTINGS:
        groups[item["district"]].append(item)

    rows = []
    for district, items in groups.items():
        rows.append(
            {
                "district": district,
                "count": len(items),
                "avgUnitPrice": round_or_none(avg([i["unitPriceYuanM2"] for i in items])),
                "medianUnitPrice": round_or_none(median([i["unitPriceYuanM2"] for i in items])),
                "avgTotalPrice": round_or_none(avg([i["totalPriceWan"] for i in items])),
                "avgArea": round_or_none(avg([i["areaM2"] for i in items])),
            }
        )
    return sorted(rows, key=lambda row: row["avgUnitPrice"] or 0, reverse=True)


def distribution(items: list[dict], field: str, bins: list[tuple[str, float, float]]) -> list[dict]:
    rows = []
    for label, low, high in bins:
        count = sum(
            1
            for item in items
            if item[field] is not None and low <= float(item[field]) < high
        )
        rows.append({"label": label, "count": count})
    return rows


def api_summary() -> dict:
    districts = group_by_district()
    reliable_districts = [row for row in districts if row["count"] >= 50]
    highest = reliable_districts[0] if reliable_districts else None
    lowest = reliable_districts[-1] if reliable_districts else None
    newest_time = max((item["crawlTime"] for item in LISTINGS if item["crawlTime"]), default="")

    return {
        "rawCount": len(LISTINGS),
        "validCount": len(VALID_LISTINGS),
        "districtCount": len({item["district"] for item in LISTINGS}),
        "communityCount": len({item["community"] for item in LISTINGS if item["community"]}),
        "avgUnitPrice": round_or_none(avg([i["unitPriceYuanM2"] for i in VALID_LISTINGS])),
        "medianUnitPrice": round_or_none(median([i["unitPriceYuanM2"] for i in VALID_LISTINGS])),
        "avgTotalPrice": round_or_none(avg([i["totalPriceWan"] for i in VALID_LISTINGS])),
        "avgArea": round_or_none(avg([i["areaM2"] for i in VALID_LISTINGS])),
        "highestUnitDistrict": highest,
        "lowestUnitDistrict": lowest,
        "latestCrawlTime": newest_time,
        "missingCoreCount": len(LISTINGS) - len(VALID_LISTINGS),
    }


def api_price_distribution() -> list[dict]:
    return distribution(
        VALID_LISTINGS,
        "totalPriceWan",
        [
            ("0-50万", 0, 50),
            ("50-100万", 50, 100),
            ("100-150万", 100, 150),
            ("150-200万", 150, 200),
            ("200-300万", 200, 300),
            ("300-500万", 300, 500),
            ("500-1000万", 500, 1000),
            ("1000万以上", 1000, float("inf")),
        ],
    )


def api_area_distribution() -> list[dict]:
    return distribution(
        VALID_LISTINGS,
        "areaM2",
        [
            ("50㎡以下", 0, 50),
            ("50-70㎡", 50, 70),
            ("70-90㎡", 70, 90),
            ("90-110㎡", 90, 110),
            ("110-140㎡", 110, 140),
            ("140-200㎡", 140, 200),
            ("200㎡以上", 200, float("inf")),
        ],
    )


def api_room_layout() -> list[dict]:
    counter: Counter[int] = Counter()
    for item in VALID_LISTINGS:
        room_count = item["roomCount"]
        if room_count is not None:
            counter[room_count] += 1
    return [{"roomCount": key, "count": counter[key]} for key in sorted(counter)]


def room_bucket(room_count: int | None) -> str | None:
    if room_count is None or room_count <= 0:
        return None
    if room_count >= 5:
        return "5室及以上"
    return f"{room_count}室"


def api_district_room_heatmap() -> dict:
    district_counts = Counter(item["district"] for item in VALID_LISTINGS if item["district"])
    districts = [
        district
        for district, count in district_counts.most_common()
        if count >= 50
    ][:12]
    room_labels = ["1室", "2室", "3室", "4室", "5室及以上"]

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in VALID_LISTINGS:
        label = room_bucket(item["roomCount"])
        if item["district"] in districts and label in room_labels:
            groups[(item["district"], label)].append(item)

    cells = []
    for district in districts:
        for label in room_labels:
            items = groups.get((district, label), [])
            cells.append(
                {
                    "district": district,
                    "roomLabel": label,
                    "count": len(items),
                    "avgUnitPrice": round_or_none(avg([i["unitPriceYuanM2"] for i in items])),
                    "avgTotalPrice": round_or_none(avg([i["totalPriceWan"] for i in items])),
                }
            )
    return {"districts": districts, "roomLabels": room_labels, "cells": cells}


def api_district_unit_price_boxplot() -> list[dict]:
    groups: dict[str, list[int]] = defaultdict(list)
    for item in VALID_LISTINGS:
        if item["district"] and item["unitPriceYuanM2"] is not None:
            groups[item["district"]].append(item["unitPriceYuanM2"])

    rows = []
    for district, values in groups.items():
        if len(values) < 50:
            continue
        rows.append(
            {
                "district": district,
                "count": len(values),
                "p10": round_or_none(percentile(values, 0.1)),
                "q1": round_or_none(percentile(values, 0.25)),
                "median": round_or_none(percentile(values, 0.5)),
                "q3": round_or_none(percentile(values, 0.75)),
                "p90": round_or_none(percentile(values, 0.9)),
                "avgUnitPrice": round_or_none(avg(values)),
            }
        )
    return sorted(rows, key=lambda row: row["median"] or 0, reverse=True)[:14]


def api_orientation_distribution() -> list[dict]:
    counter: Counter[str] = Counter()
    for item in VALID_LISTINGS:
        orientation = item["orientation"] or "未知"
        counter[orientation] += 1
    return [
        {"label": label, "count": count}
        for label, count in counter.most_common(12)
    ]


def api_tag_distribution() -> list[dict]:
    counter: Counter[str] = Counter()
    for item in VALID_LISTINGS:
        counter.update(item["tags"])
    return [
        {"label": label, "count": count}
        for label, count in counter.most_common(14)
    ]


def field_missing_count(field: str) -> int:
    count = 0
    for item in LISTINGS:
        value = item.get(field)
        if value is None or value == "" or value == []:
            count += 1
    return count


def api_data_quality() -> dict:
    fields = [
        ("district", "区县"),
        ("community", "小区"),
        ("areaM2", "面积"),
        ("layout", "户型"),
        ("roomCount", "室数"),
        ("hallCount", "厅数"),
        ("orientation", "朝向"),
        ("totalPriceWan", "总价"),
        ("unitPriceYuanM2", "单价"),
        ("tags", "标签"),
        ("coverImageUrl", "封面图"),
    ]
    total = max(1, len(LISTINGS))
    rows = []
    for field, label in fields:
        missing = field_missing_count(field)
        rows.append(
            {
                "field": field,
                "label": label,
                "missing": missing,
                "complete": len(LISTINGS) - missing,
                "completeRate": round((len(LISTINGS) - missing) / total * 100, 2),
            }
        )

    dedup_counter = Counter(item["dedupKey"] for item in LISTINGS if item["dedupKey"])
    source_id_counter = Counter(item["sourceListingId"] for item in LISTINGS if item["sourceListingId"])
    duplicate_dedup = sum(count - 1 for count in dedup_counter.values() if count > 1)
    duplicate_source_id = sum(count - 1 for count in source_id_counter.values() if count > 1)
    return {
        "rawCount": len(LISTINGS),
        "validCount": len(VALID_LISTINGS),
        "validRate": round(len(VALID_LISTINGS) / total * 100, 2),
        "missingCoreCount": len(LISTINGS) - len(VALID_LISTINGS),
        "duplicateDedupKeyCount": duplicate_dedup,
        "duplicateSourceIdCount": duplicate_source_id,
        "fields": rows,
    }


def pearson(x_values: list[float], y_values: list[float]) -> float | None:
    pairs = [(x, y) for x, y in zip(x_values, y_values) if x is not None and y is not None]
    if len(pairs) < 2:
        return None
    xs = [pair[0] for pair in pairs]
    ys = [pair[1] for pair in pairs]
    x_mean = avg(xs)
    y_mean = avg(ys)
    if x_mean is None or y_mean is None:
        return None
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    x_denominator = math.sqrt(sum((x - x_mean) ** 2 for x in xs))
    y_denominator = math.sqrt(sum((y - y_mean) ** 2 for y in ys))
    if x_denominator == 0 or y_denominator == 0:
        return None
    return numerator / (x_denominator * y_denominator)


def correlation_strength(value: float | None) -> str:
    if value is None:
        return "不可计算"
    absolute = abs(value)
    if absolute >= 0.7:
        return "强相关"
    if absolute >= 0.4:
        return "中等相关"
    if absolute >= 0.2:
        return "弱相关"
    return "相关性较弱"


def api_correlations() -> list[dict]:
    metrics = [
        ("面积与总价", "areaM2", "totalPriceWan"),
        ("面积与单价", "areaM2", "unitPriceYuanM2"),
        ("总价与单价", "totalPriceWan", "unitPriceYuanM2"),
        ("房间数与面积", "roomCount", "areaM2"),
        ("房间数与总价", "roomCount", "totalPriceWan"),
    ]
    rows = []
    for label, x_field, y_field in metrics:
        value = pearson(
            [item[x_field] for item in VALID_LISTINGS],
            [item[y_field] for item in VALID_LISTINGS],
        )
        rows.append(
            {
                "label": label,
                "coefficient": round_or_none(value, 3),
                "strength": correlation_strength(value),
            }
        )
    return rows


def api_top_communities() -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in VALID_LISTINGS:
        if item["community"]:
            groups[(item["district"], item["community"])].append(item)

    rows = []
    for (district, community), items in groups.items():
        if len(items) < 4:
            continue
        rows.append(
            {
                "district": district,
                "community": community,
                "label": f"{community}（{district}）",
                "count": len(items),
                "avgUnitPrice": round_or_none(avg([i["unitPriceYuanM2"] for i in items])),
                "avgTotalPrice": round_or_none(avg([i["totalPriceWan"] for i in items])),
                "avgArea": round_or_none(avg([i["areaM2"] for i in items])),
            }
        )
    return sorted(rows, key=lambda row: (row["count"], row["avgUnitPrice"] or 0), reverse=True)[:14]


def segment_listing(item: dict) -> str:
    unit_price = item["unitPriceYuanM2"] or 0
    total_price = item["totalPriceWan"] or 0
    area = item["areaM2"] or 0
    if total_price >= 500 or area >= 200:
        return "高端大宅型"
    if unit_price >= 20000:
        return "核心高价型"
    if area >= 110 and 100 <= total_price < 500:
        return "改善居住型"
    if total_price < 100 or area < 90:
        return "刚需紧凑型"
    if unit_price < 8000:
        return "低单价潜力型"
    return "主流均衡型"


def api_market_segments() -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in VALID_LISTINGS:
        groups[segment_listing(item)].append(item)

    segment_order = [
        "刚需紧凑型",
        "主流均衡型",
        "改善居住型",
        "低单价潜力型",
        "核心高价型",
        "高端大宅型",
    ]
    rows = []
    for label in segment_order:
        items = groups.get(label, [])
        if not items:
            continue
        rows.append(
            {
                "label": label,
                "count": len(items),
                "share": round(len(items) / max(1, len(VALID_LISTINGS)) * 100, 1),
                "avgUnitPrice": round_or_none(avg([i["unitPriceYuanM2"] for i in items])),
                "avgTotalPrice": round_or_none(avg([i["totalPriceWan"] for i in items])),
                "avgArea": round_or_none(avg([i["areaM2"] for i in items])),
            }
        )
    return rows


def api_value_districts() -> list[dict]:
    rows = [row for row in group_by_district() if row["count"] >= 50 and row["avgUnitPrice"]]
    if not rows:
        return []

    min_price = min(row["avgUnitPrice"] for row in rows)
    max_price = max(row["avgUnitPrice"] for row in rows)
    max_count = max(row["count"] for row in rows)
    price_range = max(max_price - min_price, 1)

    result = []
    for row in rows:
        price_score = (max_price - row["avgUnitPrice"]) / price_range
        supply_score = row["count"] / max_count
        value_score = price_score * 70 + supply_score * 30
        if row["avgUnitPrice"] <= 8000:
            level = "低单价机会区"
        elif value_score >= 55:
            level = "均衡推荐区"
        elif row["avgUnitPrice"] >= 15000:
            level = "核心高价区"
        else:
            level = "普通观察区"
        result.append(
            {
                **row,
                "valueScore": round(value_score, 1),
                "level": level,
            }
        )
    return sorted(result, key=lambda row: row["valueScore"], reverse=True)


def api_district_quadrants() -> list[dict]:
    rows = [row for row in group_by_district() if row["count"] >= 50]
    if not rows:
        return []
    count_mid = median([row["count"] for row in rows]) or 0
    price_mid = median([row["avgUnitPrice"] for row in rows if row["avgUnitPrice"] is not None]) or 0

    result = []
    for row in rows:
        high_price = (row["avgUnitPrice"] or 0) >= price_mid
        high_supply = row["count"] >= count_mid
        if high_price and high_supply:
            quadrant = "高价高供给"
        elif high_price:
            quadrant = "高价低供给"
        elif high_supply:
            quadrant = "低价高供给"
        else:
            quadrant = "低价低供给"
        result.append({**row, "quadrant": quadrant})
    return sorted(result, key=lambda row: (row["quadrant"], -row["count"]))


def api_scatter(query: dict[str, list[str]]) -> list[dict]:
    limit = max(100, min(to_int(query.get("limit", ["1200"])[0]) or 1200, 3000))
    if len(VALID_LISTINGS) <= limit:
        sample = VALID_LISTINGS
    else:
        step = max(1, len(VALID_LISTINGS) // limit)
        sample = VALID_LISTINGS[::step][:limit]
    return [
        {
            "areaM2": item["areaM2"],
            "unitPriceYuanM2": item["unitPriceYuanM2"],
            "totalPriceWan": item["totalPriceWan"],
            "district": item["district"],
            "community": item["community"],
            "title": item["title"],
        }
        for item in sample
    ]


def apply_listing_filters(query: dict[str, list[str]]) -> list[dict]:
    district = (query.get("district", [""])[0] or "").strip()
    keyword = (query.get("keyword", [""])[0] or "").strip().lower()
    min_price = to_float(query.get("min_price", [""])[0])
    max_price = to_float(query.get("max_price", [""])[0])
    min_area = to_float(query.get("min_area", [""])[0])
    max_area = to_float(query.get("max_area", [""])[0])

    rows = VALID_LISTINGS
    if district:
        rows = [item for item in rows if item["district"] == district]
    if keyword:
        rows = [
            item
            for item in rows
            if keyword in item["title"].lower() or keyword in item["community"].lower()
        ]
    if min_price is not None:
        rows = [item for item in rows if item["totalPriceWan"] is not None and item["totalPriceWan"] >= min_price]
    if max_price is not None:
        rows = [item for item in rows if item["totalPriceWan"] is not None and item["totalPriceWan"] <= max_price]
    if min_area is not None:
        rows = [item for item in rows if item["areaM2"] is not None and item["areaM2"] >= min_area]
    if max_area is not None:
        rows = [item for item in rows if item["areaM2"] is not None and item["areaM2"] <= max_area]

    sort = query.get("sort", ["unit_desc"])[0]
    sorters = {
        "unit_desc": ("unitPriceYuanM2", True),
        "unit_asc": ("unitPriceYuanM2", False),
        "total_desc": ("totalPriceWan", True),
        "total_asc": ("totalPriceWan", False),
        "area_desc": ("areaM2", True),
        "area_asc": ("areaM2", False),
    }
    field, reverse = sorters.get(sort, sorters["unit_desc"])
    return sorted(rows, key=lambda item: item[field] or 0, reverse=reverse)


def api_houses(query: dict[str, list[str]]) -> dict:
    rows = apply_listing_filters(query)
    page = max(1, to_int(query.get("page", ["1"])[0]) or 1)
    page_size = max(6, min(to_int(query.get("page_size", ["12"])[0]) or 12, 60))
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "total": len(rows),
        "page": page,
        "pageSize": page_size,
        "items": rows[start:end],
    }


def api_options() -> dict:
    units = [item["unitPriceYuanM2"] for item in VALID_LISTINGS]
    totals = [item["totalPriceWan"] for item in VALID_LISTINGS]
    areas = [item["areaM2"] for item in VALID_LISTINGS]
    return {
        "districts": sorted({item["district"] for item in LISTINGS}),
        "unitPriceRange": [min(units), max(units)] if units else [None, None],
        "totalPriceRange": [min(totals), max(totals)] if totals else [None, None],
        "areaRange": [min(areas), max(areas)] if areas else [None, None],
    }


def api_conclusions() -> list[str]:
    summary = api_summary()
    districts = [row for row in group_by_district() if row["count"] >= 50]
    by_count = sorted(districts, key=lambda row: row["count"], reverse=True)
    price_dist = api_price_distribution()
    largest_price_bin = max(price_dist, key=lambda row: row["count"], default=None)

    conclusions = []
    if summary["highestUnitDistrict"] and summary["lowestUnitDistrict"]:
        high = summary["highestUnitDistrict"]
        low = summary["lowestUnitDistrict"]
        conclusions.append(
            f"{high['district']}样本均价最高，约{high['avgUnitPrice']}元/㎡；{low['district']}均价较低，约{low['avgUnitPrice']}元/㎡。"
        )
    if by_count:
        conclusions.append(
            f"样本主要集中在{by_count[0]['district']}，共有{by_count[0]['count']}套，占有效样本的{round(by_count[0]['count'] / max(1, len(VALID_LISTINGS)) * 100, 1)}%。"
        )
    if largest_price_bin:
        conclusions.append(
            f"总价分布中，{largest_price_bin['label']}房源最多，共{largest_price_bin['count']}套。"
        )
    conclusions.append(
        f"本数据集有效房源{summary['validCount']}套，覆盖{summary['districtCount']}个区县，可支撑区县对比、价格分布、面积分布和房源筛选展示。"
    )
    return conclusions


def is_allowed_image_url(raw_url: str) -> bool:
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"}:
        return False
    hostname = parsed.hostname or ""
    return any(hostname == host or hostname.endswith(f".{host}") for host in ALLOWED_IMAGE_HOSTS)


def fetch_remote_image(raw_url: str) -> tuple[bytes, str]:
    if not raw_url or not is_allowed_image_url(raw_url):
        raise ValueError("Image host is not allowed")

    request = Request(
        raw_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Referer": "https://m.fang.com/esf/cq/",
        },
    )
    with urlopen(request, timeout=8) as response:
        content_type = response.headers.get("Content-Type", "image/jpeg").split(";")[0]
        if not content_type.startswith("image/"):
            raise ValueError(f"Remote content is not an image: {content_type}")
        return response.read(), content_type


class DashboardHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        print(f"[server] {self.address_string()} - {format % args}")

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, payload, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, route_path: str) -> None:
        relative = "index.html" if route_path == "/" else unquote(route_path.removeprefix("/static/"))
        file_path = (STATIC_DIR / relative).resolve()
        if not str(file_path).startswith(str(STATIC_DIR.resolve())) or not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Static file not found")
            return
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        body = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)

        try:
            if route == "/":
                self.send_static("/")
            elif route in {"/app.js", "/styles.css"}:
                self.send_static(f"/static{route}")
            elif route.startswith("/static/"):
                self.send_static(route)
            elif route == "/health":
                self.send_json({"status": "ok", "rows": len(LISTINGS), "validRows": len(VALID_LISTINGS)})
            elif route == "/api/summary":
                self.send_json(api_summary())
            elif route == "/api/options":
                self.send_json(api_options())
            elif route == "/api/stats/districts":
                self.send_json(group_by_district())
            elif route == "/api/stats/price-distribution":
                self.send_json(api_price_distribution())
            elif route == "/api/stats/area-distribution":
                self.send_json(api_area_distribution())
            elif route == "/api/stats/room-layout":
                self.send_json(api_room_layout())
            elif route == "/api/stats/district-room-heatmap":
                self.send_json(api_district_room_heatmap())
            elif route == "/api/stats/district-unit-price-boxplot":
                self.send_json(api_district_unit_price_boxplot())
            elif route == "/api/stats/orientations":
                self.send_json(api_orientation_distribution())
            elif route == "/api/stats/tags":
                self.send_json(api_tag_distribution())
            elif route == "/api/stats/scatter":
                self.send_json(api_scatter(query))
            elif route == "/api/analysis/data-quality":
                self.send_json(api_data_quality())
            elif route == "/api/analysis/correlations":
                self.send_json(api_correlations())
            elif route == "/api/analysis/top-communities":
                self.send_json(api_top_communities())
            elif route == "/api/analysis/market-segments":
                self.send_json(api_market_segments())
            elif route == "/api/analysis/value-districts":
                self.send_json(api_value_districts())
            elif route == "/api/analysis/district-quadrants":
                self.send_json(api_district_quadrants())
            elif route == "/api/houses":
                self.send_json(api_houses(query))
            elif route == "/api/analysis/conclusions":
                self.send_json(api_conclusions())
            elif route == "/api/image":
                image_url = query.get("url", [""])[0]
                body, content_type = fetch_remote_image(image_url)
                self.send_bytes(body, content_type)
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "Route not found")
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            if route == "/api/image":
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)


def run() -> None:
    host = "127.0.0.1"
    port = to_int(os.environ.get("PORT")) or 8765
    if not DATA_FILE.exists():
        print(f"Data file not found: {DATA_FILE}")
    print(f"Loaded {len(LISTINGS)} rows from {DATA_FILE}")
    print(f"Dashboard: http://{host}:{port}")
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    server.serve_forever()


if __name__ == "__main__":
    run()
