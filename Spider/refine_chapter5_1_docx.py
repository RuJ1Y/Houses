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
    preferred = downloads / "学年设计文档v1_第4章细化版_4.1已改.docx"
    if preferred.exists():
        return preferred
    matches = sorted(downloads.glob("*4.1*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
    if matches:
        return matches[0]
    raise FileNotFoundError("未找到 4.1 已改文档")


def text_of(element: ET.Element) -> str:
    return "".join(t.text or "" for t in element.findall(f".//{qn('t')}")).strip()


def paragraphs(body: ET.Element) -> list[ET.Element]:
    return [child for child in list(body) if child.tag == qn("p")]


def make_paragraph(template: ET.Element, text: str) -> ET.Element:
    paragraph = deepcopy(template)
    p_pr = paragraph.find(qn("pPr"))
    paragraph.clear()
    if p_pr is not None:
        paragraph.append(deepcopy(p_pr))
    run = ET.SubElement(paragraph, qn("r"))
    t = ET.SubElement(run, qn("t"))
    t.text = text
    if text.startswith(" ") or text.endswith(" "):
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return paragraph


def find_index(items: list[ET.Element], text: str, start: int = 0) -> int:
    for index, item in enumerate(items[start:], start=start):
        if text_of(item) == text:
            return index
    raise ValueError(f"未找到段落：{text}")


def write_docx(source: Path, document_xml: bytes, output: Path) -> None:
    with ZipFile(source, "r") as zin, ZipFile(output, "w", ZIP_DEFLATED) as zout:
        for name in zin.namelist():
            zout.writestr(name, document_xml if name == "word/document.xml" else zin.read(name))


def main() -> None:
    source = find_source()
    downloads_output = source.with_name("学年设计文档v1_第4章细化版_4.1_5.1已改.docx")
    workspace_output = Path.cwd() / downloads_output.name

    with ZipFile(source, "r") as z:
        root = ET.fromstring(z.read("word/document.xml"))

    body = root.find(qn("body"))
    if body is None:
        raise ValueError("document.xml 缺少 body")

    ps = paragraphs(body)
    start = find_index(ps, "5.1 数据整理（清洗与存储）实现采用的开发工具和环境", 20)
    end = find_index(ps, "5.2 数据清洗和存储具体实现及代码", start)

    heading_template = ps[start]
    body_template = ps[start + 1]

    content = [
        ("h", "5.1 数据整理（清洗与存储）实现采用的开发工具和环境"),
        ("b", "本项目数据整理、清洗与存储部分所使用的开发工具和环境如下："),
        ("b", "操作系统：Windows 11"),
        ("b", "开发工具：VS Code / PyCharm（清洗脚本编写与调试）、PowerShell（执行清洗命令与查看输出报告）"),
        ("b", "数据管理：CSV / JSONL / JSON 文件，使用 Excel、文本编辑器或脚本查看清洗前后数据和清洗报告"),
        ("b", "版本控制：Git / GitHub（清洗脚本和文档版本管理）"),
        ("b", "编程语言与库："),
        ("b", "Python 3.10（主要开发语言）"),
        ("b", "csv（读取合并数据集并写入标准化CSV文件）"),
        ("b", "json（生成清洗报告JSON文件）"),
        ("b", "re（户型解析、文本规范化和字段提取）"),
        ("b", "pathlib / argparse / datetime（路径管理、命令行参数和报告生成时间记录）"),
        ("b", "collections（统计删除原因、数据源数量和区县分布）"),
        ("b", "数据文件目录："),
        ("b", "data/raw（保存原始采集数据、合并数据和采集日志）"),
        ("b", "data/clean（保存清洗后的标准化数据集和清洗报告）"),
        ("b", "核心脚本：clean_house_data.py（完成字段标准化、缺失值处理、异常值过滤和重复数据标记/删除）"),
    ]

    new_elements = [
        make_paragraph(heading_template if kind == "h" else body_template, text)
        for kind, text in content
    ]

    body_children = list(body)
    start_pos = body_children.index(ps[start])
    end_pos = body_children.index(ps[end])
    for element in body_children[start_pos:end_pos]:
        body.remove(element)
    for offset, element in enumerate(new_elements):
        body.insert(start_pos + offset, element)

    document_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    write_docx(source, document_xml, workspace_output)
    shutil.copy2(workspace_output, downloads_output)
    print(f"wrote: {downloads_output}")
    print(f"workspace copy: {workspace_output}")


if __name__ == "__main__":
    main()
