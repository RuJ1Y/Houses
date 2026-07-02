from __future__ import annotations

import shutil
from copy import deepcopy
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ET.register_namespace("w", W_NS)


def qn(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def find_source() -> Path:
    downloads = Path.home() / "Downloads"
    preferred = downloads / "学年设计文档v1_第4_5章已完成.docx"
    if preferred.exists():
        return preferred
    matches = list(downloads.glob("*4_5*.docx"))
    if matches:
        return matches[0]
    raise FileNotFoundError("未找到第4_5章已完成文档")


def block_text(element: ET.Element) -> str:
    return "".join(t.text or "" for t in element.findall(f".//{qn('t')}"))


def iter_paragraphs(body: ET.Element) -> list[ET.Element]:
    return [child for child in list(body) if child.tag == qn("p")]


def make_paragraph(template: ET.Element, text: str) -> ET.Element:
    paragraph = deepcopy(template)
    p_pr = paragraph.find(qn("pPr"))
    paragraph.clear()
    if p_pr is not None:
        paragraph.append(deepcopy(p_pr))
    if text:
        run = ET.SubElement(paragraph, qn("r"))
        t = ET.SubElement(run, qn("t"))
        t.text = text
        if text.startswith(" ") or text.endswith(" "):
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return paragraph


def write_docx(source: Path, document_xml: bytes, output: Path) -> None:
    with ZipFile(source, "r") as zin, ZipFile(output, "w", ZIP_DEFLATED) as zout:
        for name in zin.namelist():
            zout.writestr(name, document_xml if name == "word/document.xml" else zin.read(name))


def find_para_index(paragraphs: list[ET.Element], text: str, start: int = 0) -> int:
    for i, paragraph in enumerate(paragraphs[start:], start=start):
        if block_text(paragraph).strip() == text:
            return i
    raise ValueError(f"未找到段落：{text}")


def main() -> None:
    source = find_source()
    downloads_output = source.with_name("学年设计文档v1_第4章细化版.docx")
    workspace_output = Path.cwd() / downloads_output.name

    with ZipFile(source, "r") as z:
        root = ET.fromstring(z.read("word/document.xml"))

    body = root.find(qn("body"))
    if body is None:
        raise ValueError("document.xml 缺少 body")

    paragraphs = iter_paragraphs(body)
    p_texts = [block_text(p).strip() for p in paragraphs]

    # The document contains a table of contents before the body. Use the known
    # body section boundaries to avoid replacing TOC entries.
    start_para = 129
    end_para = 181

    h2_template = paragraphs[start_para]
    h3_template = paragraphs[find_para_index(paragraphs, "4.3.1 数据采集模块实现")]
    body_template = paragraphs[start_para + 1]

    content: list[tuple[str, str]] = [
        ("h2", "4.2 项目的整体功能"),
        ("body", "本节所述整体功能主要指“数据获取与实现”部分，即系统如何从目标网站获取重庆二手房源原始数据，并将其保存为后续清洗和分析可以直接使用的结构化文件。该部分不包含第5章的数据清洗逻辑，也不包含第6章的可视化展示逻辑，而是重点说明爬虫采集、字段解析、分页控制、区县覆盖、采集日志和原始数据存储等功能。"),
        ("body", "数据获取模块首先根据重庆二手房源的实际数据来源确定采集对象，项目最终采用房天下移动端和到家了移动端两个数据源。房天下移动端爬虫由mobile_fang_listing_spider.py实现，到家了移动端爬虫由daojiale_listing_spider.py实现。两个脚本的作用并不是简单下载网页，而是按照区县、页码和筛选条件批量请求房源列表页面，并从页面或接口返回内容中提取结构化房源字段。"),
        ("body", "从功能流程上看，数据获取模块包括六个步骤：第一，读取命令行参数，确定目标采集数量、采集区县、最大页数、请求延时、失败重试次数和是否追加已有数据；第二，根据区县和页码构造请求地址；第三，发送HTTP请求并判断页面是否正常返回；第四，解析页面中的房源卡片，提取标题、小区、户型、面积、总价、单价、朝向、标签和图片链接等字段；第五，将解析出的字段转换为统一的数据结构；第六，将采集结果写入CSV/JSONL文件，并同步记录采集日志。"),
        ("body", "该模块支持按区县覆盖采集，能够避免只采集主城区或单一区域导致样本分布不均的问题。运行时可以通过--by-district参数按区县逐个采集，也可以通过--district参数指定重点区县。对于房源较少的区县，脚本会在连续多页没有新增数据后自动停止；对于房源较多的区县，脚本会继续翻页直到达到最大页数或目标采集数量。"),
        ("body", "数据获取模块的输出结果主要包括三类文件：第一类是原始房源CSV文件，用于保存表格化房源数据；第二类是JSONL文件，用于按行保存结构化记录，方便后续排查单条原始数据；第三类是采集日志CSV文件，用于记录每一页的采集状态、新增数量和累计数量。通过这些文件，系统可以完整保留从采集到清洗前的原始数据过程。"),
        ("h2", "4.3 各个功能模块的实现"),
        ("h3", "4.3.1 命令行参数与采集控制实现"),
        ("body", "爬虫脚本通过命令行参数控制采集行为，便于在不修改代码的情况下调整采集范围和采集速度。例如，--target-count用于设置目标采集数量，--max-pages用于限制每个区县或筛选条件下最多翻页数量，--delay用于控制请求间隔，--max-empty-pages用于设置连续空页停止阈值，--append-existing用于在已有数据基础上追加采集结果。"),
        ("code", "python mobile_fang_listing_spider.py --by-district --target-count 50000 --max-pages 3000 --delay 1.5 --max-empty-pages 200 --append-existing"),
        ("body", "上述命令表示按区县依次采集房天下移动端数据，目标数量为50000条，每个采集任务最多翻到3000页，每次请求之间延时1.5秒。如果连续200页没有新增房源，则认为当前区县或筛选条件已经基本采完，程序会自动切换到下一个采集任务。--append-existing表示保留已有CSV中的数据，在此基础上继续追加新采集结果，适合中途停止后继续采集。"),
        ("h3", "4.3.2 页面请求与异常处理实现"),
        ("body", "爬虫请求页面时会设置浏览器请求头、超时时间和重试次数。请求头的作用是让服务器识别为正常浏览器访问，超时时间用于避免网络长时间无响应导致程序卡住，重试机制用于处理临时网络波动。请求失败、返回空页或被验证页拦截时，脚本会记录状态并继续后续任务。"),
        ("code", "headers = {"),
        ("code", "    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36',"),
        ("code", "    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',"),
        ("code", "}"),
        ("code", "response = session.get(page_url, headers=headers, timeout=args.timeout)"),
        ("code", "html = response.text"),
        ("body", "这段代码体现了请求阶段的核心逻辑：session.get负责访问具体页面，headers用于携带浏览器标识，timeout用于限制请求等待时间。实际脚本中还会结合retries参数进行失败重试，并在控制台输出当前区县、页码、new数量和total数量，便于实时观察采集是否正常推进。"),
        ("h3", "4.3.3 房源字段解析实现"),
        ("body", "页面请求成功后，脚本需要从列表页中解析房源卡片。由于本项目只采集列表页字段，不进入详情页，因此解析逻辑主要围绕列表页中已经展示的信息展开。解析字段包括source、city、district、page、source_listing_id、title、area_m2、layout、room_count、hall_count、orientation、community、tags、total_price_wan、unit_price_yuan_m2、cover_image_url、is_new和crawl_time。"),
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
        ("body", "该字典是爬虫输出的核心数据结构。source用于区分数据来源，district用于后续区域统计，page记录数据来自第几页，source_listing_id用于保留平台房源编号，area_m2、total_price_wan和unit_price_yuan_m2是后续价格分析的核心数值字段，layout、room_count和hall_count用于户型分析，cover_image_url用于前端展示封面图片。通过统一字段名，不同网站采集到的数据可以在后续合并阶段对齐。"),
        ("h3", "4.3.4 户型与数值字段提取实现"),
        ("body", "列表页中的面积、总价、单价和户型通常是文本形式，不能直接用于统计分析，因此爬虫会在解析时进行初步转换。例如，将“89.5㎡”转换为浮点数89.5，将“120万”转换为120，将“3室2厅”拆分为room_count=3和hall_count=2。"),
        ("code", "match = re.search(r'(\\d+)室(?:(\\d+)厅)?', layout or '')"),
        ("code", "if match:"),
        ("code", "    room_count = int(match.group(1))"),
        ("code", "    hall_count = int(match.group(2) or 0)"),
        ("body", "这段代码用于从户型文本中提取室数和厅数。正则表达式中的第一个分组匹配“室”前面的数字，第二个分组匹配“厅”前面的数字。如果原始文本只有“1室”而没有厅数，则厅数默认为0。这样可以保证后续户型结构图和区域×户型热力图有可用的数值字段。"),
        ("h3", "4.3.5 原始数据保存实现"),
        ("body", "爬虫采集到的数据会写入CSV文件和JSONL文件。CSV适合表格化查看和后续清洗，JSONL适合保留逐条记录，便于出现字段异常时回溯原始数据。写入CSV时使用utf-8-sig编码，方便Windows环境下用Excel打开不乱码。"),
        ("code", "def write_csv(output, rows, fieldnames):"),
        ("code", "    output.parent.mkdir(parents=True, exist_ok=True)"),
        ("code", "    with output.open('w', newline='', encoding='utf-8-sig') as file:"),
        ("code", "        writer = csv.DictWriter(file, fieldnames=fieldnames)"),
        ("code", "        writer.writeheader()"),
        ("code", "        writer.writerows(rows)"),
        ("body", "该函数首先确保输出目录存在，然后以utf-8-sig编码创建CSV文件。csv.DictWriter根据fieldnames固定字段顺序，writeheader写入表头，writerows批量写入房源数据。这样即使不同数据源字段解析顺序不同，最终输出文件仍然保持统一列顺序，便于第5章清洗脚本读取。"),
        ("h3", "4.3.6 采集日志实现"),
        ("body", "采集日志用于记录爬虫每一页的运行状态。日志字段包括采集时间、区县、页码、状态、新增数量和累计数量。通过日志可以判断采集是否正常，例如某个区县连续多页new=0，说明该区县可能已经没有更多可获取房源；如果状态为request_error，则说明请求阶段出现网络异常。"),
        ("code", "log_rows.append({"),
        ("code", "    'crawl_time': datetime.now().isoformat(timespec='seconds'),"),
        ("code", "    'district': district,"),
        ("code", "    'page': page,"),
        ("code", "    'status': status,"),
        ("code", "    'new_count': len(new_items),"),
        ("code", "    'total': len(all_items),"),
        ("code", "})"),
        ("body", "这段代码在每次页面处理结束后追加一条日志。crawl_time记录当前时间，district和page定位采集位置，status说明页面状态，new_count记录当前页新增房源数量，total记录累计数量。后续排查采集不足、空页过多或中途停止问题时，日志可以直接反映采集过程。"),
    ]

    templates = {"h2": h2_template, "h3": h3_template, "body": body_template, "code": body_template}
    new_elements = [make_paragraph(templates[kind], text) for kind, text in content]

    body_children = list(body)
    start_element = paragraphs[start_para]
    end_element = paragraphs[end_para]
    start_pos = body_children.index(start_element)
    end_pos = body_children.index(end_element)

    for element in body_children[start_pos:end_pos]:
        body.remove(element)
    for offset, element in enumerate(new_elements):
        body.insert(start_pos + offset, element)

    document_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    write_docx(source, document_xml, workspace_output)
    shutil.copy2(workspace_output, downloads_output)

    print(f"source: {source}")
    print(f"wrote: {downloads_output}")
    print(f"workspace copy: {workspace_output}")


if __name__ == "__main__":
    main()
