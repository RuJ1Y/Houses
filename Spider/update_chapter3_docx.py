from __future__ import annotations

import shutil
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ET.register_namespace("w", W_NS)


def qn(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def find_document() -> Path:
    matches = list((Path.home() / "Downloads").glob("*v1.docx"))
    if not matches:
        raise FileNotFoundError("未找到 Downloads 下的 *v1.docx")
    return matches[0]


def block_text(element: ET.Element) -> str:
    return "".join(t.text or "" for t in element.findall(f".//{qn('t')}"))


def iter_blocks(body: ET.Element) -> list[tuple[str, ET.Element]]:
    blocks: list[tuple[str, ET.Element]] = []
    for child in list(body):
        local = child.tag.split("}", 1)[-1]
        if local == "p":
            blocks.append(("p", child))
        elif local == "tbl":
            blocks.append(("tbl", child))
    return blocks


def set_paragraph_text(paragraph: ET.Element, text: str) -> None:
    p_pr = paragraph.find(qn("pPr"))
    paragraph.clear()
    if p_pr is not None:
        paragraph.append(p_pr)
    run = ET.SubElement(paragraph, qn("r"))
    t = ET.SubElement(run, qn("t"))
    t.text = text
    if text.startswith(" ") or text.endswith(" "):
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def set_cell_text(cell: ET.Element, text: str) -> None:
    paragraphs = cell.findall(qn("p"))
    if paragraphs:
        first = paragraphs[0]
        set_paragraph_text(first, text)
        for extra in paragraphs[1:]:
            cell.remove(extra)
    else:
        p = ET.SubElement(cell, qn("p"))
        set_paragraph_text(p, text)


def set_table_rows(table: ET.Element, rows: list[list[str]]) -> None:
    trs = table.findall(qn("tr"))
    if not trs:
        raise ValueError("表格没有行，无法更新")

    while len(trs) < len(rows):
        clone = deepcopy(trs[-1])
        table.append(clone)
        trs.append(clone)

    while len(trs) > len(rows):
        table.remove(trs[-1])
        trs.pop()

    for tr, row in zip(trs, rows):
        cells = tr.findall(qn("tc"))
        while len(cells) < len(row):
            clone = deepcopy(cells[-1])
            tr.append(clone)
            cells.append(clone)
        for index, cell in enumerate(cells):
            set_cell_text(cell, row[index] if index < len(row) else "")


def write_docx_from_dir(src_docx: Path, temp_dir: Path, output_docx: Path) -> None:
    with ZipFile(src_docx, "r") as zin:
        names = zin.namelist()
        with ZipFile(output_docx, "w", ZIP_DEFLATED) as zout:
            for name in names:
                if name == "word/document.xml":
                    data = (temp_dir / "document.xml").read_bytes()
                else:
                    data = zin.read(name)
                zout.writestr(name, data)


def main() -> None:
    source = find_document()
    output = source.with_name(source.stem + "_第3章已修改.docx")
    workspace_output = Path.cwd() / output.name

    with ZipFile(source, "r") as z:
        document_xml = z.read("word/document.xml")

    root = ET.fromstring(document_xml)
    body = root.find(qn("body"))
    if body is None:
        raise ValueError("word/document.xml 缺少 body")
    blocks = iter_blocks(body)

    paragraph_updates = {
        88: "本系统采用分层架构设计，整体分为表现层、后端接口层、数据处理层和数据文件层。表现层基于HTML、CSS和JavaScript构建，通过调用后端API获取统计数据，并使用Canvas和自定义图表组件完成可视化展示。后端接口层基于Python HTTP Server实现，负责读取清洗后的CSV数据文件，根据前端展示需求计算统计指标，并以JSON格式返回数据。数据处理层由独立清洗脚本完成，负责对不同来源房源数据进行字段统一、类型转换、缺失值处理、异常值过滤和重复数据标记或删除。数据文件层用于保存原始数据、合并数据、采集日志和清洗后的标准化数据，主要格式为CSV和JSONL。系统不依赖MySQL或SQLite数据库，后端直接读取清洗后的CSV文件完成查询和统计分析，结构简单、部署方便，适合本项目数据规模和课程设计需求。",
        90: "系统划分为以下五大功能模块：",
        91: "模块名称 核心功能 子功能说明",
        92: "数据采集模块 爬虫采集与原始数据保存 ①通过mobile_fang_listing_spider.py采集房天下移动端重庆二手房数据；②通过daojiale_listing_spider.py采集到家了移动端数据；③按区县、分页和筛选条件采集房源字段，并保存为CSV/JSONL原始数据文件",
        93: "数据清洗模块 数据合并、标准化与去重 ①统一不同来源字段；②转换面积、总价、单价、室数、厅数等字段类型；③过滤面积和价格异常数据；④处理缺失字段；⑤生成去重键并标记或删除重复房源；⑥输出标准化CSV数据集和清洗报告",
        94: "数据可视化模块 Web图表展示 ①区域均价对比；②价格分布直方图；③面积区间分布；④面积-价格散点图；⑤户型结构；⑥区域×户型热力图；⑦区域性价比、市场分层、热门小区、标签、朝向和相关性分析展示",
        95: "统计分析模块 指标计算与结论输出 ①基于清洗后的数据计算均值、中位数、分布和样本量；②按区县、户型、小区、标签等维度聚合统计；③计算面积、总价、单价、室数等字段相关性；④自动生成区域价格、市场结构和房源特征分析结论",
        96: "系统管理模块 数据维护与运行检查 ①查看采集日志和清洗报告；②按需要重新运行爬虫或清洗脚本；③通过后端健康检查接口查看数据加载状态；④通过前端筛选条件检查房源列表和统计结果",
        99: "系统核心数据文件关系如下：",
        100: "· 原始数据文件：包括房天下移动端房源数据、到家了移动端房源数据以及对应采集日志，保存采集到的未经清洗的房源记录。",
        101: "· 合并数据文件：将不同来源的原始房源数据按统一字段进行合并，作为后续清洗处理的输入。",
        102: "· 标准化数据文件：由清洗脚本生成，包含统一字段、规范数值、异常过滤结果、去重键和重复标记，是后端接口和前端可视化使用的主要数据源。",
        103: "关系说明：不同来源的原始数据经过合并和清洗后生成标准化数据集，Web后端直接读取标准化CSV文件进行统计计算；采集日志和清洗报告用于记录数据处理过程，与房源记录不建立数据库外键关系。",
        105: "标准化房源数据文件（chongqing_fang_daojiale_cleaned.csv）",
        107: "采集日志文件（mobile_fang_crawl_log.csv / daojiale_crawl_log.csv）",
        113: "前端页面加载时通过Ajax并发调用多个统计接口，后端从清洗后的CSV数据文件中读取数据，在内存中完成分组聚合、分布统计、相关性计算和分页筛选，并返回JSON格式结果；前端解析接口返回的数据后，使用HTML、CSS、JavaScript、Canvas和自定义图表组件动态渲染统计卡片、柱状图、散点图、热力图和房源列表。筛选条件如区县、关键词、价格区间、排序方式等通过请求参数传递，后端根据参数过滤内存数据后返回对应结果。",
        118: "爬虫层：根据目标移动端页面结构进行分页采集，设置请求头、访问延时、超时时间、失败重试和空页停止条件，降低请求失败率，并避免对目标网站造成过高访问压力。",
        119: "数据层：原始数据、合并数据和清洗数据分文件保存，清洗阶段过滤缺失核心字段、异常面积、异常价格和重复房源，减少无效数据对后续统计分析的影响。",
        120: "后端层：服务启动时读取清洗后的CSV文件并保存在内存中，统计接口直接基于内存数据进行聚合计算，避免每次请求重复读取文件；散点图接口采用抽样返回，减少前端渲染压力。",
        122: "爬虫设置合理User-Agent、请求延时、超时和重试机制，控制访问频率，降低因高频请求导致访问异常的风险。",
        123: "系统不涉及用户注册、登录和个人隐私信息存储，仅处理公开展示的房源信息，并保存房源字段、图片链接和采集时间等业务数据。",
        124: "后端接口对分页、筛选、排序、价格区间等请求参数进行基本校验和范围限制，避免异常参数影响服务运行；系统未使用SQL数据库，因此不存在SQL注入风险。",
    }

    for index, text in paragraph_updates.items():
        kind, element = blocks[index]
        if kind != "p":
            raise ValueError(f"BLOCK {index} 不是段落")
        set_paragraph_text(element, text)

    house_rows = [
        ["字段名", "类型", "说明", "约束", "", ""],
        ["source", "VARCHAR", "数据来源，如mobile_fang、daojiale_mobile", "NOT NULL", "", ""],
        ["city", "VARCHAR", "城市名称", "NOT NULL", "", ""],
        ["district", "VARCHAR", "所属区县", "NOT NULL", "", ""],
        ["page", "INT", "采集页码", "", "", ""],
        ["source_listing_id", "VARCHAR", "来源平台房源编号", "", "", ""],
        ["title", "VARCHAR", "房源标题", "NOT NULL", "", ""],
        ["area_m2", "FLOAT", "建筑面积（㎡）", "NOT NULL", "", ""],
        ["layout", "VARCHAR", "户型文本，如3室2厅", "", "", ""],
        ["room_count", "INT", "室数", "", "", ""],
        ["hall_count", "INT", "厅数", "", "", ""],
        ["orientation", "VARCHAR", "朝向", "", "", ""],
        ["community", "VARCHAR", "小区名称", "", "", ""],
        ["tags", "VARCHAR", "房源标签，使用竖线分隔", "", "", ""],
        ["total_price_wan", "FLOAT", "挂牌总价（万元）", "NOT NULL", "", ""],
        ["unit_price_yuan_m2", "FLOAT", "单价（元/㎡）", "NOT NULL", "", ""],
        ["cover_image_url", "VARCHAR", "封面图片链接", "", "", ""],
        ["is_new", "INT", "是否新房源，1表示是，0表示否", "DEFAULT 0", "", ""],
        ["crawl_time", "DATETIME", "采集时间", "", "", ""],
        ["dedup_key", "VARCHAR", "去重键", "", "", ""],
        ["is_duplicate", "INT", "重复标记，1表示重复", "DEFAULT 0", "", ""],
    ]

    log_rows = [
        ["字段名", "类型", "说明", "约束", "", ""],
        ["crawl_time", "DATETIME", "采集时间", "", "", ""],
        ["source", "VARCHAR", "数据来源或脚本名称", "", "", ""],
        ["district", "VARCHAR", "采集区县", "", "", ""],
        ["page", "INT", "采集页码", "", "", ""],
        ["route", "VARCHAR", "数据源路由或区县标识", "", "", ""],
        ["status", "VARCHAR", "采集状态，如成功、空页、失败", "", "", ""],
        ["new_count", "INT", "当前页新增记录数", "", "", ""],
        ["total", "INT", "当前累计采集记录数", "", "", ""],
        ["remark", "VARCHAR", "错误信息或备注", "", "", ""],
        ["说明", "", "本项目采用CSV/JSONL文件存储，配置简单、便于查看和备份，能够满足约5万条房源数据的分析展示需求。", "", "", ""],
    ]

    api_rows = [
        ["接口", "方法", "功能", "返回数据"],
        ["/api/summary", "GET", "获取数据概览", "统计卡片JSON"],
        ["/api/options", "GET", "获取筛选选项", "区县、价格和面积范围"],
        ["/api/stats/districts", "GET", "各区县均价统计", "区县统计数组"],
        ["/api/stats/price-distribution", "GET", "价格分布直方图数据", "分箱统计数组"],
        ["/api/stats/area-distribution", "GET", "面积区间分布数据", "分箱统计数组"],
        ["/api/stats/room-layout", "GET", "户型结构统计", "室数统计数组"],
        ["/api/stats/scatter", "GET", "面积-价格散点数据", "[{areaM2,totalPriceWan,district}]"],
        ["/api/stats/district-room-heatmap", "GET", "区域×户型热力图数据", "{districts,roomLabels,cells}"],
        ["/api/stats/tags", "GET", "房源标签统计", "标签统计数组"],
        ["/api/stats/orientations", "GET", "朝向结构统计", "朝向统计数组"],
        ["/api/analysis/top-communities", "GET", "热门小区样本", "小区统计数组"],
        ["/api/analysis/correlations", "GET", "相关性分析", "相关系数数组"],
        ["/api/analysis/conclusions", "GET", "自动生成分析结论", "文本结论数组"],
        ["/api/houses", "GET", "获取房源列表，支持分页、筛选和排序", "房源JSON数组"],
        ["/api/image", "GET", "代理加载房源封面图片", "图片二进制或错误JSON"],
    ]

    tech_rows = [
        ["层次", "技术选型"],
        ["开发语言", "Python3.10"],
        ["爬虫", "Requests脚本（mobile_fang_listing_spider.py、daojiale_listing_spider.py）"],
        ["数据处理", "Python清洗脚本（clean_house_data.py）"],
        ["数据存储", "CSV/JSONL文件"],
        ["后端框架", "Python HTTP Server轻量接口服务"],
        ["前端图表", "HTML+CSS+JavaScript+Canvas/自定义图表组件"],
        ["前端基础", "HTML+CSS+JavaScript原生，无额外框架依赖"],
        ["分析方法", "统计分析、分组聚合、相关性分析"],
        ["开发工具", "VSCode/PyCharm代码编辑与调试，PowerShell运行脚本"],
        ["版本控制", "Git/GitHub用于代码管理与备份"],
    ]

    tables = [(i, b[1]) for i, b in enumerate(blocks) if b[0] == "tbl"]
    table_by_block = {index: element for index, element in tables}
    set_table_rows(table_by_block[106], house_rows)
    set_table_rows(table_by_block[108], log_rows)
    set_table_rows(table_by_block[111], api_rows)
    set_table_rows(table_by_block[115], tech_rows)

    with TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        (temp_dir / "document.xml").write_bytes(
            ET.tostring(root, encoding="utf-8", xml_declaration=True)
        )
        write_docx_from_dir(source, temp_dir, workspace_output)

    shutil.copy2(workspace_output, output)
    print(f"wrote: {output}")
    print(f"workspace copy: {workspace_output}")


if __name__ == "__main__":
    main()
