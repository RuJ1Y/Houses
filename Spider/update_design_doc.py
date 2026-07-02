import copy
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


SRC = Path(r"C:\Users\wzw\Downloads\学年设计文档v1.docx")
OUT = Path(r"D:\Work\House\Houses\Spider\学年设计文档_按实际项目修改版.docx")

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
ET.register_namespace("w", W_NS)


def qn(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def para_text(p: ET.Element) -> str:
    return "".join(t.text or "" for t in p.findall(".//w:t", NS)).strip()


def set_para_text(p: ET.Element, text: str) -> None:
    for child in list(p):
        if child.tag != qn("pPr"):
            p.remove(child)
    r = ET.SubElement(p, qn("r"))
    t = ET.SubElement(r, qn("t"))
    t.set(qn("space"), "preserve")
    t.text = text


def make_para(text: str, style: str | None = None, sample_ppr: ET.Element | None = None) -> ET.Element:
    p = ET.Element(qn("p"))
    if sample_ppr is not None:
        p.append(copy.deepcopy(sample_ppr))
    elif style:
        ppr = ET.SubElement(p, qn("pPr"))
        pstyle = ET.SubElement(ppr, qn("pStyle"))
        pstyle.set(qn("val"), style)
    r = ET.SubElement(p, qn("r"))
    t = ET.SubElement(r, qn("t"))
    t.set(qn("space"), "preserve")
    t.text = text
    return p


def get_sample_ppr(body: ET.Element, exact_text: str) -> ET.Element | None:
    for child in body:
        if child.tag == qn("p") and para_text(child) == exact_text:
            ppr = child.find("w:pPr", NS)
            return copy.deepcopy(ppr) if ppr is not None else None
    return None


def update_toc(body: ET.Element) -> None:
    replacements = {
        "第1章 概述1": "第1章 概述",
        "第2章 系统分析和可行性分析1": "第2章 系统分析和可行性分析",
        "第3章 系统设计1": "第3章 系统设计",
        "第4章 数据获取与实现1": "第4章 数据获取与实现",
        "4.1项目实现采用的开发工具和环境1": "4.1 项目实现采用的开发工具和环境",
        "4.2项目的整体功能1": "4.2 项目的整体功能",
        "4.3各个功能模块的实现1": "4.3 各个功能模块的实现",
        "第5章 数据整理（清洗与存储）实现1": "第5章 数据整理（清洗与存储）实现",
        "5.1数据整理（清晰与存储）实现采用的开发工具和环境1": "5.1 数据整理实现采用的开发工具和环境",
        "5.2数据清洗和存储具体实现及代码2": "5.2 数据清洗和存储具体实现及代码",
        "第6章 数据分析与可视化实现2": "第6章 数据分析与可视化实现",
        "6.1数据分析与可视化实现采用的开发工具和环境2": "6.1 数据分析与可视化实现采用的开发工具和环境",
        "6.2项目的整体功能的实现2": "6.2 项目的整体功能的实现",
        "第7章 总结与展望2": "第7章 总结与展望",
    }
    for child in body:
        if child.tag == qn("p"):
            text = para_text(child)
            if text in replacements:
                set_para_text(child, replacements[text])


CONTENT = [
    ("h1", "第1章 概述"),
    ("h2", "1.1 项目背景"),
    ("p", "随着重庆二手房挂牌信息持续增长，购房者在比较不同区县、小区、户型和价格区间时，往往需要同时查看多个平台的数据。单个平台的挂牌信息存在覆盖范围有限、重复房源较多、字段格式不统一等问题，难以直接支撑系统化分析。因此，本项目围绕“重庆市二手房源价格数据分析”主题，设计并实现了从数据采集、数据清洗、数据合并到结构化存储的完整数据处理流程。"),
    ("p", "项目实际采用房天下移动端和到家了移动端接口作为主要数据源，分别通过 mobile_fang_listing_spider.py 和 daojiale_listing_spider.py 采集重庆各区县二手房源信息。采集后的数据经过 clean_house_data.py 清洗整理，形成可用于后续统计分析和可视化展示的标准化 CSV 数据集。"),
    ("h2", "1.2 项目目标"),
    ("p", "本项目的核心目标是获取不少于 5 万条重庆市具体二手房源数据，并对原始数据进行规范化处理，使其能够支持后续价格分析、区域对比和可视化展示。具体目标包括：一是编写稳定可运行的爬虫脚本，从多个公开房产平台采集房源数据；二是统一不同平台的数据字段，形成一致的数据结构；三是对缺失值、异常值、重复房源进行清洗处理；四是将处理结果保存为 CSV、JSONL 和日志文件，便于检查、复用和进一步分析。"),
    ("h2", "1.3 项目意义"),
    ("p", "本项目将课堂中学习的 Python 网络请求、文本解析、文件读写、数据清洗等知识应用到真实数据场景中。通过处理真实平台的反爬、分页、字段缺失、重复数据等问题，项目不仅能够得到较大规模的重庆二手房源数据，也能锻炼团队处理复杂数据源和构建数据处理流水线的能力。"),
    ("h1", "第2章 系统分析和可行性分析"),
    ("h2", "2.1 需求分析"),
    ("p", "根据项目任务要求，系统首先需要完成重庆市二手房源数据采集，数据量不少于 5 万条，并尽量覆盖多个区县。每条房源数据需要包含区县、小区、标题、面积、户型、室数、厅数、朝向、总价、单价、封面图片、是否新上、采集时间等字段。其次，系统需要对不同来源的数据进行整理和清洗，删除无效数据，标记或删除重复房源，并输出最终可分析的数据文件。"),
    ("p", "结合实际开发情况，项目重点完成了数据采集和数据清洗两个核心模块。可视化和后续建模分析可基于清洗后的数据继续扩展。"),
    ("h2", "2.2 数据源可行性分析"),
    ("p", "开发过程中对房天下、58 同城、诸葛找房、到家了等平台进行了测试。房天下 PC 端存在验证页问题，因此最终采用房天下移动端列表数据。58 同城移动端虽然能够返回部分列表，但在连续请求时容易出现反爬验证和重复分页问题，去重后有效新增数据较少。诸葛找房移动端字段较少、数据量不足，最终作为备选数据源。到家了移动端提供 JSON 接口，字段结构清晰，分页和区域筛选较稳定，因此被确定为主要补充数据源。"),
    ("h2", "2.3 技术可行性"),
    ("p", "项目使用 Python 3.10 开发，主要依赖 requests 标准 HTTP 请求库和 Python 内置 csv、json、hashlib、pathlib 等模块即可完成主体功能。数据以 CSV 和 JSONL 文件保存，不依赖复杂数据库部署，适合学年设计周期内快速实现和验证。爬虫脚本均设置了 User-Agent、请求延时、超时重试、日志记录、中断保存等机制，能够满足实验性数据采集需求。"),
    ("h2", "2.4 法律与伦理可行性"),
    ("p", "本项目采集的数据来源于公开展示的房源挂牌页面或公开接口，仅用于课程设计和学习分析，不采集用户隐私数据，不进行商业化使用。爬虫运行时设置了请求延时和最大页数限制，避免对目标网站造成异常压力。"),
    ("h1", "第3章 系统设计"),
    ("h2", "3.1 总体架构"),
    ("p", "项目采用“数据采集层—数据整理层—数据存储层”的轻量化架构。数据采集层由两个爬虫脚本组成：mobile_fang_listing_spider.py 负责采集房天下移动端房源列表，daojiale_listing_spider.py 负责采集到家了移动端接口数据。数据整理层由 clean_house_data.py 完成字段标准化、异常过滤、空值处理和重复识别。数据存储层以 CSV、JSONL 和日志 CSV 文件为主，便于直接用 Excel、Python 或后续可视化程序读取。"),
    ("h2", "3.2 数据字段设计"),
    ("p", "为了统一两个平台的数据格式，项目将最终房源字段设计为：source、city、district、page、source_listing_id、title、area_m2、layout、room_count、hall_count、orientation、community、tags、total_price_wan、unit_price_yuan_m2、cover_image_url、is_new、crawl_time、dedup_key。"),
    ("p", "其中 source 表示数据来源，district 表示区县，source_listing_id 表示平台原始房源编号，dedup_key 是由脚本生成的去重辅助标识。is_new 字段用于标记新上房源，空值统一补为 0。"),
    ("h2", "3.3 文件存储设计"),
    ("p", "房天下原始数据默认保存为 data/raw/chongqing_mobile_fang_listings.csv 和 data/raw/chongqing_mobile_fang_listings.jsonl；到家了原始数据默认保存为 data/raw/chongqing_daojiale_listings.csv 和 data/raw/chongqing_daojiale_listings.jsonl；两个平台的运行日志分别保存为 mobile_fang_crawl_log.csv 和 daojiale_crawl_log.csv。合并后的数据保存为 data/raw/chongqing_fang_daojiale_merged.csv，清洗后的数据保存到 data/clean 目录。"),
    ("h1", "第4章 数据获取与实现"),
    ("h2", "4.1 开发工具和环境"),
    ("p", "项目在 Windows 环境下开发，工作目录为 D:\\Work\\House\\Houses\\Spider。主要开发语言为 Python 3.10，使用 PowerShell 执行脚本命令，核心依赖为 requests。项目未使用 Scrapy 框架，而是采用 requests.Session 维护请求会话，并通过 argparse 实现命令行参数配置。"),
    ("h2", "4.2 房天下移动端爬虫实现"),
    ("p", "房天下爬虫脚本为 mobile_fang_listing_spider.py。该脚本面向 https://m.fang.com/esf/cq/ 移动端二手房列表页，支持按区县爬取、筛选扩展、断点续爬、追加已有数据、空页停止和日志记录。脚本输出字段与统一字段保持一致，并根据区县筛选入口直接写入 district 字段。"),
    ("p", "由于房天下 PC 端 cq.esf.fang.com 多次返回 verification pages，项目放弃 PC 端入口，改用移动端列表页。移动端在部分区县和筛选条件下能够稳定返回房源列表，但非主城区县房源较少，因此需要结合第二数据源补充。"),
    ("h2", "4.3 到家了接口爬虫实现"),
    ("p", "到家了爬虫脚本为 daojiale_listing_spider.py。该脚本使用到家了移动端接口 https://m.daojiale.com/cq/ershoufangPage 作为数据来源。接口返回 JSON 数据，包含 houseid、housetitle、areaname、districtname、buildname、fang、ting、wei、builtarea、saletotal、saleprice、housecx、housezx、listUrl 等字段。"),
    ("p", "脚本将接口字段转换为统一字段：houseid 对应 source_listing_id，housetitle 对应 title，areaname 对应 district，buildname 对应 community，fang/ting/wei 组合生成 layout，builtarea 对应 area_m2，saletotal 对应 total_price_wan，saleprice 对应 unit_price_yuan_m2，housecx 对应 orientation，listUrl 对应 cover_image_url。"),
    ("p", "到家了脚本支持按区县 areaId 爬取，也支持价格、户型、面积筛选扩展。常用命令为：python daojiale_listing_spider.py --by-district --expand-filters --target-count 50000 --max-pages 30 --delay 1 --max-empty-pages 3 --per-filter-count 300。"),
    ("h2", "4.4 数据合并结果"),
    ("p", "项目最终将房天下数据和到家了数据合并，合并文件为 data/raw/chongqing_fang_daojiale_merged.csv。合并前房天下数据为 19469 条，到家了数据为 33760 条，合并后共 53229 条，满足不少于 5 万条具体二手房源数据的任务要求。"),
    ("h1", "第5章 数据整理（清洗与存储）实现"),
    ("h2", "5.1 清洗脚本和处理环境"),
    ("p", "数据清洗脚本为 clean_house_data.py。脚本读取合并后的 CSV 文件，输出清洗后的 CSV 文件和 JSON 清洗报告。脚本默认输入可通过 --input 指定，默认输出可通过 --output 指定，报告路径可通过 --report 指定。"),
    ("h2", "5.2 清洗规则"),
    ("p", "清洗脚本主要完成以下处理：去除字符串字段前后空格，统一 city 和 district，规范 area_m2、total_price_wan、unit_price_yuan_m2 的数字格式，从 layout 中提取 room_count 和 hall_count，从 tags 中辅助补充 orientation，统一 is_new 空值为 0，标准化标签分隔符，生成或保留 dedup_key。"),
    ("p", "根据最新清洗要求，脚本默认删除任意字段为空的数据行，即 source、city、district、page、source_listing_id、title、area_m2、layout、room_count、hall_count、orientation、community、tags、total_price_wan、unit_price_yuan_m2、cover_image_url、is_new、crawl_time、dedup_key 任一字段为空时，该行会被剔除。若需要保留空字段行，可添加 --keep-empty-fields 参数。"),
    ("p", "异常值过滤规则包括：缺少面积或总价的数据删除，面积小于 5㎡ 或大于 1000㎡ 的数据删除，总价小于 1 万或大于 10000 万的数据删除。"),
    ("h2", "5.3 重复数据处理"),
    ("p", "早期版本只使用 dedup_key 判断重复，而 dedup_key 包含平台房源 ID 和标题，当同一套房源在平台中出现不同 ID 或标题略有差异时，无法识别为重复。根据实际清洗中发现的“中粮中央公园祥云C区”等重复样例，脚本已改为使用房源特征判断重复。"),
    ("p", "当前重复判断规则为：district + normalized_community + area_m2 + room_count + hall_count + total_price_wan。也就是说，只要区县、小区、面积、室数、厅数、总价一致，即使 source_listing_id 不同，也会被标记为重复。默认情况下重复数据不会直接删除，而是在 is_duplicate 字段中标记；若运行时添加 --drop-duplicates，则会直接删除重复房源。"),
    ("h2", "5.4 清洗运行结果"),
    ("p", "以 data/raw/chongqing_fang_daojiale_merged.csv 为输入运行清洗脚本后，原始数据 53229 条。删除空字段、缺失面积或价格、面积异常等无效数据后，得到清洗数据 47773 条。采用新的房源特征重复判断后，标记重复数据 5179 条，其中 is_duplicate=0 的非重复记录 42594 条。"),
    ("p", "清洗脚本常用命令为：python clean_house_data.py --input data/raw/chongqing_fang_daojiale_merged.csv --output data/clean/chongqing_fang_daojiale_cleaned.csv --report data/clean/chongqing_fang_daojiale_clean_report.json。若需要直接删除重复房源，可使用：python clean_house_data.py --input data/raw/chongqing_fang_daojiale_merged.csv --output data/clean/chongqing_fang_daojiale_cleaned_dedup.csv --report data/clean/chongqing_fang_daojiale_clean_dedup_report.json --drop-duplicates。"),
    ("h1", "第6章 数据分析与可视化实现"),
    ("h2", "6.1 当前数据分析基础"),
    ("p", "当前项目已完成数据采集、合并和清洗，形成了可直接用于分析的数据集。清洗后的数据包含区县、小区、面积、户型、总价、单价、朝向、标签、图片链接等字段，能够支持区县均价统计、户型价格对比、面积与总价关系分析、小区挂牌价格统计等后续可视化任务。"),
    ("h2", "6.2 后续可视化方向"),
    ("p", "后续可基于清洗后的 CSV 数据开发可视化页面，例如：各区县平均单价柱状图、总价分布直方图、面积—总价散点图、区县—户型交叉统计热力图、热门小区挂牌量排行、不同朝向房源均价对比等。由于当前阶段重点是数据采集和清洗，Web 可视化系统可作为后续扩展模块继续完善。"),
    ("h1", "第7章 总结与展望"),
    ("h2", "7.1 项目工作总结"),
    ("p", "本项目围绕重庆市二手房源数据获取与清洗任务，完成了两个主要数据源的爬虫脚本开发，并将不同平台字段统一为一致的数据结构。项目实际使用 mobile_fang_listing_spider.py 采集房天下移动端数据，使用 daojiale_listing_spider.py 采集到家了移动端接口数据，最终合并得到 53229 条原始房源数据。"),
    ("p", "在数据整理阶段，项目使用 clean_house_data.py 对合并数据进行标准化处理，删除无效数据和空字段数据，改进重复识别规则，并输出清洗后的 CSV 文件和 JSON 报告。清洗后得到 47773 条完整记录，其中 5179 条被标记为重复，为后续去重分析提供依据。"),
    ("h2", "7.2 问题与解决"),
    ("p", "项目开发过程中遇到的主要问题包括：部分网站返回验证页、部分平台分页重复、不同平台字段不一致、房源 ID 不同但实际房源重复、部分字段存在空值等。针对这些问题，项目分别采取了更换移动端数据源、增加请求延时和空页停止、统一字段结构、使用房源特征判断重复、默认删除空字段数据等措施。"),
    ("h2", "7.3 展望"),
    ("p", "后续可继续扩展更多数据源，例如安居客、贝壳或其他本地中介平台；也可以将 CSV 存储升级为 SQLite 数据库，便于按区县、小区、价格区间快速查询。同时，可在清洗后的数据基础上开发 ECharts 可视化页面，进一步实现房价空间分布、价格区间结构和热门小区对比分析。"),
    ("p", "结束语：通过本次学年设计，团队完成了真实数据采集和清洗流程，对网络请求、反爬处理、字段标准化、异常数据处理和重复数据识别有了更深入的理解，为后续数据分析和可视化系统开发奠定了基础。"),
]


def main() -> None:
    with zipfile.ZipFile(SRC, "r") as zin:
        document_xml = zin.read("word/document.xml")
        root = ET.fromstring(document_xml)
        body = root.find("w:body", NS)
        if body is None:
            raise RuntimeError("DOCX body not found")

        update_toc(body)

        h1_ppr = get_sample_ppr(body, "第1章 概述")
        h2_ppr = get_sample_ppr(body, "1.1项目背景")
        normal_ppr = get_sample_ppr(body, "近年来，重庆二手房市场交易持续活跃，主城都市区存量房交易占比已超过新房，房价成为反映城市区域价值与人口流向的重要指标。受山地地形和“多中心、组团式”城市格局影响，重庆各板块房价差异显著，核心区与拓展区单价差距可达2~3倍。然而，当前购房者获取房价信息主要依赖中介推介和零散挂牌数据，缺乏系统化、可视化的分析工具辅助判断。与此同时，Python爬虫、数据挖掘与Web可视化技术的成熟，使得快速构建从数据采集到分析展示的完整系统成为可能。基于此，本项目以重庆市二手房源为研究对象，开展数据采集、清洗、可视化与挖掘分析工作。")

        children = list(body)
        start_idx = None
        sect_pr = None
        for i, child in enumerate(children):
            if child.tag == qn("p") and para_text(child) == "第1章 概述":
                start_idx = i
                break
        if start_idx is None:
            raise RuntimeError("正文起始位置未找到")
        if children and children[-1].tag == qn("sectPr"):
            sect_pr = children[-1]
        for child in children[start_idx:]:
            if child is not sect_pr:
                body.remove(child)

        for kind, text in CONTENT:
            if kind == "h1":
                body.insert(len(body) - (1 if sect_pr is not None and sect_pr in list(body) else 0), make_para(text, sample_ppr=h1_ppr))
            elif kind == "h2":
                body.insert(len(body) - (1 if sect_pr is not None and sect_pr in list(body) else 0), make_para(text, sample_ppr=h2_ppr))
            else:
                body.insert(len(body) - (1 if sect_pr is not None and sect_pr in list(body) else 0), make_para(text, sample_ppr=normal_ppr))

        new_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)

        OUT.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "word/document.xml":
                    data = new_xml
                zout.writestr(item, data)

    print(OUT)


if __name__ == "__main__":
    main()
