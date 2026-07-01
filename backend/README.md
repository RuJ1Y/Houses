# 重庆二手房源 Web 可视化后端

本目录用于本地 Web 数据可视化演示。当前版本不依赖 FastAPI 或前端构建工具，使用 Python 标准库读取 CSV、提供 JSON 接口并托管静态页面。

## 数据文件

```text
Spider/data/raw/chongqing_mobile_fang_listings.csv
```

当前数据规模：

```text
原始行数：19469
有效行数：19212
覆盖区县：36
```

## 启动

在项目根目录执行：

```bash
python backend/server.py
```

浏览器打开：

```text
http://127.0.0.1:8000
```

健康检查：

```text
http://127.0.0.1:8000/health
```

## 主要接口

```text
GET /api/summary
GET /api/options
GET /api/stats/districts
GET /api/stats/price-distribution
GET /api/stats/area-distribution
GET /api/stats/room-layout
GET /api/stats/scatter
GET /api/houses?page=1&page_size=12
GET /api/analysis/conclusions
```

## 页面内容

```text
顶部指标卡
区县均价排行
总价区间分布
面积区间分布
面积与单价散点图
户型结构
自动分析结论
房源列表与筛选
```
