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
    preferred = downloads / "学年设计文档v1_第4章细化版.docx"
    if preferred.exists():
        return preferred
    matches = sorted(downloads.glob("*4*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        raise FileNotFoundError("未找到第4章细化版文档")
    return matches[0]


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
    downloads_output = source.with_name("学年设计文档v1_第4章细化版_4.1已改.docx")
    workspace_output = Path.cwd() / downloads_output.name

    with ZipFile(source, "r") as z:
        root = ET.fromstring(z.read("word/document.xml"))

    body = root.find(qn("body"))
    if body is None:
        raise ValueError("document.xml 缺少 body")

    ps = paragraphs(body)
    chapter4 = find_index(ps, "第4章 数据获取与实现")
    start = find_index(ps, "4.1 项目实现采用的开发工具和环境", chapter4)
    end = find_index(ps, "4.2 项目的整体功能", start)

    heading_template = ps[start]
    body_template = ps[start + 1]

    content = [
        ("h", "4.1 项目实现采用的开发工具和环境"),
        ("b", "本项目数据获取与实现部分所使用的开发工具和环境如下："),
        ("b", "操作系统：Windows 11"),
        ("b", "开发工具：VS Code / PyCharm（代码编写与调试）、PowerShell（脚本运行与日志查看）"),
        ("b", "数据管理：CSV / JSONL 文件，使用 Excel 或文本编辑器查看原始采集结果和采集日志"),
        ("b", "版本控制：Git / GitHub（代码管理与备份）"),
        ("b", "编程语言与库："),
        ("b", "Python 3.10（主要开发语言）"),
        ("b", "Requests（网络请求与页面获取）"),
        ("b", "csv / json（原始数据与日志文件读写）"),
        ("b", "re（字段解析、户型和数值提取）"),
        ("b", "pathlib / argparse / datetime（路径管理、命令行参数和采集时间记录）"),
        ("b", "浏览器与调试工具："),
        ("b", "Chrome / Edge（目标移动端页面访问与结果验证）"),
        ("b", "Chrome DevTools（网络请求分析、页面结构查看与字段定位）"),
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
