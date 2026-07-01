# Mobile Fang listing crawler

This crawler targets the mobile Fang.com Chongqing second-hand listing pages:

```text
https://m.fang.com/esf/cq/
```

It collects concrete listing records, not aggregate price trend data.

## Run a small test

```powershell
python mobile_fang_listing_spider.py --max-pages 5 --delay 1
```

## Target 50,000 listings

```powershell
python mobile_fang_listing_spider.py --target-count 50000 --max-pages 3000 --delay 1.5
```

Outputs:

- `data/raw/chongqing_mobile_fang_listings.csv`
- `data/raw/chongqing_mobile_fang_listings.jsonl`
- `data/raw/mobile_fang_crawl_log.csv`

Fields:

- `source`
- `city`
- `page`
- `source_listing_id`
- `title`
- `area_m2`
- `layout`
- `orientation`
- `community`
- `tags`
- `total_price_wan`
- `unit_price_yuan_m2`
- `url`
- `page_url`
- `crawl_time`
- `dedup_key`
