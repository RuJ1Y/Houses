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


def find_source() -> Path:
    downloads = Path.home() / "Downloads"
    chapter3 = downloads / "学年设计文档v1_第3章已修改.docx"
    original = downloads / "学年设计文档v1.docx"
    if chapter3.exists():
        return chapter3
    if original.exists():
        return original
    matches = list(downloads.glob("*v1*.docx"))
    if not matches:
        raise FileNotFoundError("Downloads 中未找到学年设计文档")
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


def clear_paragraph_keep_style(paragraph: ET.Element) -> ET.Element:
    p_pr = paragraph.find(qn("pPr"))
    paragraph.clear()
    if p_pr is not None:
        paragraph.append(deepcopy(p_pr))
    return paragraph


def make_paragraph(template: ET.Element, text: str) -> ET.Element:
    paragraph = deepcopy(template)
    clear_paragraph_keep_style(paragraph)
    if text:
        run = ET.SubElement(paragraph, qn("r"))
        t = ET.SubElement(run, qn("t"))
        t.text = text
        if text.startswith(" ") or text.endswith(" "):
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return paragraph


def style_value(paragraph: ET.Element) -> str:
    p_style = paragraph.find(f"{qn('pPr')}/{qn('pStyle')}")
    return p_style.get(qn("val")) if p_style is not None else ""


def write_docx(src_docx: Path, document_xml: bytes, output_docx: Path) -> None:
    with ZipFile(src_docx, "r") as zin, ZipFile(output_docx, "w", ZIP_DEFLATED) as zout:
        for name in zin.namelist():
            data = document_xml if name == "word/document.xml" else zin.read(name)
            zout.writestr(name, data)


def main() -> None:
    source = find_source()
    downloads_output = source.with_name("学年设计文档v1_第4_5章已完成.docx")
    workspace_output = Path.cwd() / downloads_output.name

    with ZipFile(source, "r") as z:
        root = ET.fromstring(z.read("word/document.xml"))

    body = root.find(qn("body"))
    if body is None:
        raise ValueError("word/document.xml 缺少 body")

    blocks = iter_blocks(body)
    block_texts = [block_text(element).strip() if kind == "p" else "" for kind, element in blocks]

    start = block_texts.index("第4章 数据获取与实现")
    end = block_texts.index("第6章 数据分析与可视化实现")

    heading1_template = blocks[start][1]
    heading2_template = blocks[130][1]
    heading3_template = blocks[163][1]
    body_template = blocks[131][1]

    # Fallback if styles are unusual.
    if not style_value(heading2_template):
        heading2_template = blocks[start][1]

    content: list[tuple[str, str]] = [
        ("h1", "第4章 数据获取与实现"),
        ("h2", "4.1 项目实现采用的开发工具和环境"),
        ("body", "本章的数据获取部分主要在Windows环境下完成，项目目录为D:\\Work\\House\\Houses\\Spider，核心开发语言为Python 3.10。开发工具主要使用VS Code或PyCharm进行代码编写与调试，使用PowerShell运行爬虫脚本并查看实时采集日志，使用浏览器开发者工具分析移动端页面请求结构。数据采集依赖Requests等基础网络请求能力，未采用Scrapy框架；数据文件主要采用CSV和JSONL格式保存，便于后续检查、合并和清洗。"),
        ("body", "本项目实际使用的爬虫脚本包括mobile_fang_listing_spider.py和daojiale_listing_spider.py。其中，mobile_fang_listing_spider.py用于采集房天下移动端重庆二手房列表数据，daojiale_listing_spider.py用于采集到家了移动端重庆二手房列表数据。两个脚本均支持按区县采集、分页采集、目标数量控制、访问延时、超时重试、空页停止、追加写入和采集日志记录。"),
        ("body", "项目使用的数据目录为data/raw和data/clean。data/raw用于保存各数据源的原始采集结果和采集日志，data/clean用于保存清洗后的标准化数据集和清洗报告。通过这种目录划分，可以清楚区分原始数据、合并数据和清洗数据，便于后期复查和重新处理。"),
        ("h2", "4.2 项目的整体功能"),
        ("body", "本项目围绕重庆二手房源数据采集、整理、分析和可视化展示展开，整体功能包括数据采集、原始数据保存、数据合并、数据清洗、后端接口和前端可视化展示。数据采集阶段通过两个爬虫脚本分别从房天下移动端和到家了移动端获取房源列表数据，采集字段包括数据来源、城市、区县、页码、房源编号、标题、建筑面积、户型、室数、厅数、朝向、小区名称、标签、总价、单价、封面图片链接、是否新房源和采集时间等。"),
        ("body", "数据采集完成后，系统将不同来源的房源数据保存为CSV/JSONL文件，并通过后续清洗脚本完成字段统一、异常过滤、缺失处理和重复识别。清洗后的标准化CSV文件由Web后端直接读取，后端根据前端请求计算区域均价、价格分布、面积分布、户型结构、区域×户型热力图、热门小区和相关性分析等统计结果，并以JSON格式返回。前端页面再根据接口结果渲染统计卡片、柱状图、散点图、热力图和房源列表。"),
        ("body", "与原方案相比，当前项目没有使用MySQL/SQLite数据库，也没有实现独立的增量更新服务和机器学习建模模块，而是采用更轻量的CSV文件存储和统计分析方式。该方案部署简单、数据可直接查看，能够满足本项目5万条左右二手房源数据的采集、清洗、分析和展示需求。"),
        ("h2", "4.3 各个功能模块的实现"),
        ("h3", "4.3.1 数据采集模块实现"),
        ("body", "数据采集模块的核心是对移动端列表页进行请求和解析。爬虫按照区县和页码构造请求地址，获取页面内容后解析房源卡片，提取标题、小区、户型、面积、价格、朝向、标签和图片链接等字段。为了降低采集失败率，脚本设置了浏览器请求头、超时时间、失败重试次数、访问延时和连续空页停止条件。"),
        ("body", "以房天下移动端爬虫为例，运行命令可以写为："),
        ("code", "python mobile_fang_listing_spider.py --by-district --target-count 50000 --max-pages 3000 --delay 1.5 --max-empty-pages 200 --append-existing"),
        ("body", "到家了移动端爬虫作为补充数据源，用于扩展样本规模和区县覆盖范围，运行方式与房天下爬虫类似。采集过程中，程序会在控制台输出当前区县、页码、新增数量和累计数量，同时将采集过程写入日志文件，便于判断是否出现空页、失败页或采集停止。"),
        ("body", "数据解析后的单条房源记录统一组织为字典结构，主要字段如下："),
        ("code", "item = {"),
        ("code", "    'source': 'mobile_fang',"),
        ("code", "    'city': '重庆',"),
        ("code", "    'district': district,"),
        ("code", "    'page': page,"),
        ("code", "    'source_listing_id': listing_id,"),
        ("code", "    'title': title,"),
        ("code", "    'area_m2': area_m2,"),
        ("code", "    'layout': layout,"),
        ("code", "    'room_count': room_count,"),
        ("code", "    'hall_count': hall_count,"),
        ("code", "    'orientation': orientation,"),
        ("code", "    'community': community,"),
        ("code", "    'tags': tags,"),
        ("code", "    'total_price_wan': total_price,"),
        ("code", "    'unit_price_yuan_m2': unit_price,"),
        ("code", "    'cover_image_url': cover_image_url,"),
        ("code", "    'is_new': is_new,"),
        ("code", "    'crawl_time': crawl_time,"),
        ("code", "}"),
        ("h3", "4.3.2 原始数据保存模块实现"),
        ("body", "爬虫采集到的房源数据会同时保存为CSV和JSONL文件。CSV文件便于使用Excel或脚本直接查看，JSONL文件便于按行保存原始结构化记录，适合后期排查单条数据。项目中的原始数据主要保存在data/raw目录下，例如chongqing_mobile_fang_listings.csv、chongqing_daojiale_listings.csv以及对应采集日志文件。"),
        ("body", "保存CSV时，程序按统一字段顺序写入表头和数据行，避免不同来源字段顺序不一致影响后续合并。示例代码如下："),
        ("code", "def write_csv(output, rows, fieldnames):"),
        ("code", "    output.parent.mkdir(parents=True, exist_ok=True)"),
        ("code", "    with output.open('w', newline='', encoding='utf-8-sig') as file:"),
        ("code", "        writer = csv.DictWriter(file, fieldnames=fieldnames)"),
        ("code", "        writer.writeheader()"),
        ("code", "        writer.writerows(rows)"),
        ("h3", "4.3.3 采集日志模块实现"),
        ("body", "采集日志用于记录每次请求的关键状态，包括采集时间、数据源、区县、页码、页面状态、新增数量和累计数量等。当某一页返回空数据或请求失败时，日志可以帮助判断是该区县房源较少、页码超出范围，还是网络请求出现异常。"),
        ("body", "日志记录的核心思路如下："),
        ("code", "log_rows.append({"),
        ("code", "    'crawl_time': datetime.now().isoformat(timespec='seconds'),"),
        ("code", "    'district': district,"),
        ("code", "    'page': page,"),
        ("code", "    'status': status,"),
        ("code", "    'new_count': len(new_items),"),
        ("code", "    'total': len(all_items),"),
        ("code", "})"),
        ("h1", "第5章 数据整理（清洗与存储）实现"),
        ("h2", "5.1 数据整理（清洗与存储）实现采用的开发工具和环境"),
        ("body", "数据整理部分同样采用Python 3.10实现，核心脚本为clean_house_data.py，运行目录为D:\\Work\\House\\Houses\\Spider。清洗脚本主要使用Python标准库中的csv、json、re、datetime、pathlib和collections等模块完成文件读取、字段转换、文本规范化、异常判断和报告生成。项目没有依赖Pandas和NumPy，也没有将结果写入数据库，而是将清洗后的标准化数据继续保存为CSV文件。"),
        ("body", "清洗输入文件为data/raw/chongqing_fang_daojiale_merged.csv，输出文件为data/clean/chongqing_fang_daojiale_cleaned.csv或去重后的data/clean/chongqing_fang_daojiale_cleaned_dedup.csv。清洗报告保存为JSON文件，用于记录输入行数、输出行数、删除原因、重复标记数量、数据源分布、区县分布和字段缺失情况。"),
        ("h2", "5.2 数据清洗和存储具体实现及代码"),
        ("body", "数据清洗流程主要包括字段读取、字段标准化、数值转换、缺失值处理、异常值过滤、户型解析、标签整理、重复识别和结果保存。首先，脚本读取合并后的CSV文件，将每一行转换为字典；然后对面积、总价、单价、室数、厅数等字段进行数值化处理，对小区名称、标题、朝向、标签等文本字段进行去空格和规范化处理。"),
        ("body", "数值字段转换示例代码如下："),
        ("code", "def to_float(value):"),
        ("code", "    if value is None:"),
        ("code", "        return None"),
        ("code", "    text = str(value).strip().replace(',', '')"),
        ("code", "    if not text or text.lower() == 'nan':"),
        ("code", "        return None"),
        ("code", "    try:"),
        ("code", "        return float(text)"),
        ("code", "    except ValueError:"),
        ("code", "        return None"),
        ("body", "对于面积和价格等核心字段，清洗脚本会删除明显异常或缺失的数据。例如面积为空、总价为空、单价为空的记录不能参与价格分析；面积小于5㎡或大于1000㎡的数据被认为不符合正常住宅范围；总价小于1万元或过高的数据也会被过滤。"),
        ("code", "if area_m2 is None or total_price_wan is None or unit_price_yuan_m2 is None:"),
        ("code", "    drop_reason = 'missing_area_or_price'"),
        ("code", "elif area_m2 < 5 or area_m2 > 1000:"),
        ("code", "    drop_reason = 'abnormal_area'"),
        ("code", "elif total_price_wan < 1 or total_price_wan > 10000:"),
        ("code", "    drop_reason = 'abnormal_price'"),
        ("body", "户型字段清洗主要从“3室2厅”等文本中提取室数和厅数。当原始字段中的room_count或hall_count为空时，脚本会尝试从layout字段中解析得到，保证后续户型结构分析和区域×户型热力图能够正常使用。"),
        ("code", "match = re.search(r'(\\d+)室(?:(\\d+)厅)?', layout or '')"),
        ("code", "if match:"),
        ("code", "    room_count = int(match.group(1))"),
        ("code", "    hall_count = int(match.group(2) or 0)"),
        ("body", "重复数据识别是本项目清洗过程中的重要环节。由于不同筛选条件或不同平台可能出现相同小区、相同面积、相同户型、相同价格的房源，脚本会根据区县、小区、面积、室数、厅数和总价生成去重键，并据此标记重复数据。如果运行时加入--drop-duplicates参数，则会直接删除重复记录。"),
        ("code", "dedup_key = '|'.join(["),
        ("code", "    district,"),
        ("code", "    normalize_text(community),"),
        ("code", "    format_number(area_m2),"),
        ("code", "    str(room_count or ''),"),
        ("code", "    str(hall_count or ''),"),
        ("code", "    format_number(total_price_wan),"),
        ("code", "])"),
        ("body", "清洗完成后，脚本将标准化字段按固定顺序写入CSV文件，并生成清洗报告。标准化字段包括source、city、district、page、source_listing_id、title、area_m2、layout、room_count、hall_count、orientation、community、tags、total_price_wan、unit_price_yuan_m2、cover_image_url、is_new、crawl_time、dedup_key和is_duplicate。"),
        ("body", "执行清洗并删除重复数据的命令如下："),
        ("code", "python clean_house_data.py --input data/raw/chongqing_fang_daojiale_merged.csv --output data/clean/chongqing_fang_daojiale_cleaned_dedup.csv --report data/clean/chongqing_fang_daojiale_clean_dedup_report.json --drop-duplicates"),
        ("body", "通过上述清洗与存储流程，系统可以将不同来源、格式不完全一致的原始房源数据整理为统一、规范、可分析的标准化数据集，为后续Web接口统计和前端可视化展示提供可靠的数据基础。"),
    ]

    templates = {
        "h1": heading1_template,
        "h2": heading2_template,
        "h3": heading3_template,
        "body": body_template,
        "code": body_template,
    }

    new_elements = [make_paragraph(templates[kind], text) for kind, text in content]

    body_children = list(body)
    start_element = blocks[start][1]
    end_element = blocks[end][1]
    start_pos = body_children.index(start_element)
    end_pos = body_children.index(end_element)

    for element in body_children[start_pos:end_pos]:
        body.remove(element)
    for offset, element in enumerate(new_elements):
        body.insert(start_pos + offset, element)

    output_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    write_docx(source, output_xml, workspace_output)
    shutil.copy2(workspace_output, downloads_output)

    print(f"source: {source}")
    print(f"wrote: {downloads_output}")
    print(f"workspace copy: {workspace_output}")


if __name__ == "__main__":
    main()
