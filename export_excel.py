# -*- coding: utf-8 -*-
"""
jsonl -> 全字段 Excel 转换
输入: collected_all13_20260914.jsonl (10,182 条 x 22 字段)
输出: results/全字段数据表_13板块_20260914.xlsx
  - Sheet1 "留言数据": 全部 22 列, 表头冻结, 自动列宽, 时间/数值列格式化
  - Sheet2 "字段说明": 每个字段的含义与取值说明
"""
import json
import datetime
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

def clean(v):
    """清洗 Excel 不允许的控制字符, 保留正常换行"""
    if isinstance(v, str):
        return ILLEGAL_CHARACTERS_RE.sub("", v)
    return v

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "collected_all13_20260914.jsonl")
OUT = os.path.join(HERE, "results", "全字段数据表_13板块_20260914.xlsx")

# 列顺序: (json字段名, 中文表头, 类型)  类型: t=文本 d=日期 n=数值(2位) i=整数
COLUMNS = [
    ("tid",                "留言ID(tid)",           "i"),
    ("fid",                "板块ID",                "i"),
    ("forum_name",         "板块名称",              "t"),
    ("subject",            "留言标题",              "t"),
    ("content",            "留言正文",              "t"),
    ("type_name",          "留言类型",              "t"),
    ("domain_name",        "领域分类",              "t"),
    ("state_info",         "办理状态",              "t"),
    ("nick_name",          "用户昵称",              "t"),
    ("from",               "来源属地",              "t"),
    ("ip_place",           "IP属地",               "t"),
    ("create_dateline",    "提交时间戳",            "i"),
    ("create_date",        "提交时间",              "d"),
    ("satisfaction",       "满意度评分",            "i"),
    ("has_reply",          "是否已回复",            "i"),
    ("reply_dateline",     "回复时间戳",            "i"),
    ("reply_date",         "回复时间",              "d"),
    ("reply_delay_days",   "回复时长(天)",          "n"),
    ("reply_organization", "回复单位",              "t"),
    ("reply_nick_name",    "回复人昵称",            "t"),
    ("reply_dept_level",   "回复单位层级",          "i"),
    ("reply_content",      "回复正文",              "t"),
]

FIELD_DOCS = [
    ("tid", "留言唯一ID，主键，全表零重复"),
    ("fid", "板块ID：1217市委书记 / 1218市长 / 2813~2824为11个区级板块"),
    ("forum_name", "板块名称（如：广州市委书记冯忠华、番禺区）"),
    ("subject", "留言标题"),
    ("content", "留言正文全文"),
    ("type_name", "留言类型：建言 / 投诉求助 / 咨询 等"),
    ("domain_name", "官方领域分类：城建 / 交通 / 环保 / 教育等"),
    ("state_info", "办理状态：待回复 / 办理中 / 已办理 / 已回复 等"),
    ("nick_name", "留言用户昵称（平台脱敏）"),
    ("from", "用户属地（如：广东省 佛山市网友）"),
    ("ip_place", "IP属地"),
    ("create_dateline", "提交时间的Unix时间戳（秒）"),
    ("create_date", "提交时间（可读格式）"),
    ("satisfaction", "满意度评分，0=未评价"),
    ("has_reply", "1=已获官方回复；0=截至快照时刻未回复（生存分析中作右删失）"),
    ("reply_dateline", "首次官方回复时间的Unix时间戳；未回复=0"),
    ("reply_date", "首次官方回复时间；未回复=空"),
    ("reply_delay_days", "回复时长(天) = (回复时间戳-提交时间戳)/86400，保留3位小数；未回复=空"),
    ("reply_organization", "回复单位名称（如：广州市越秀区）；未回复=空"),
    ("reply_nick_name", "回复人昵称（平台脱敏）"),
    ("reply_dept_level", "回复单位行政层级编码"),
    ("reply_content", "回复正文全文"),
]

def main():
    rows = []
    for line in open(SRC, encoding="utf-8"):
        if line.strip():
            rows.append(json.loads(line))
    print(f"读取 {len(rows)} 条")

    wb = Workbook()

    # ---------- Sheet1 留言数据 ----------
    ws = wb.active
    ws.title = "留言数据"

    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
    body_font = Font(name="微软雅黑", size=9)
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for c, (_, head, _) in enumerate(COLUMNS, 1):
        cell = ws.cell(row=1, column=c, value=head)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
    ws.row_dimensions[1].height = 28

    ts_fmt = "yyyy-mm-dd hh:mm:ss"
    for r, d in enumerate(rows, 2):
        for c, (key, _, typ) in enumerate(COLUMNS, 1):
            v = d.get(key)
            if typ == "d":
                ts = d.get(key.replace("_date", "_dateline"))
                if key == "create_date":
                    ts = d.get("create_dateline")
                else:
                    ts = d.get("reply_dateline")
                if ts:
                    cell = ws.cell(row=r, column=c,
                                   value=datetime.datetime.fromtimestamp(int(ts)))
                    cell.number_format = ts_fmt
                else:
                    cell = ws.cell(row=r, column=c, value=None)
            elif typ == "n":
                cell = ws.cell(row=r, column=c, value=v)
                if v is not None:
                    cell.number_format = "0.000"
            elif typ == "i":
                cell = ws.cell(row=r, column=c, value=v)
            else:
                cell = ws.cell(row=r, column=c, value=clean(v))
            cell.font = body_font
            cell.border = border

    # 列宽: 按表头与样本估宽, 长文本列封顶
    width_map = {}
    for c, (key, head, typ) in enumerate(COLUMNS, 1):
        sample_max = max((len(str(d.get(key) or "")) for d in rows[:500]), default=8)
        head_w = len(head) * 2
        if key in ("content", "reply_content"):
            w = 60
        elif key == "subject":
            w = 36
        elif key == "forum_name":
            w = 20
        elif typ in ("d",):
            w = 19
        else:
            w = min(max(head_w, sample_max + 2), 26)
        width_map[c] = w
        ws.column_dimensions[get_column_letter(c)].width = w

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{len(rows)+1}"

    # ---------- Sheet2 字段说明 ----------
    ws2 = wb.create_sheet("字段说明")
    for c, h in enumerate(("字段名", "含义与取值说明"), 1):
        cell = ws2.cell(row=1, column=c, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 22
    for r, (k, doc) in enumerate(FIELD_DOCS, 2):
        ws2.cell(row=r, column=1, value=k).font = Font(name="Consolas", size=10)
        ws2.cell(row=r, column=2, value=doc).font = body_font
    ws2.column_dimensions["A"].width = 22
    ws2.column_dimensions["B"].width = 90

    wb.save(OUT)
    sz = os.path.getsize(OUT)
    print(f"已写出: {OUT}  ({sz/1024/1024:.1f} MB)")

    # 回验
    from openpyxl import load_workbook
    wb2 = load_workbook(OUT, read_only=True)
    w = wb2["留言数据"]
    print(f"回验: 行数={w.max_row-1} 列数={w.max_column} (应为 {len(rows)} x {len(COLUMNS)})")
    hdr = [c.value for c in next(w.iter_rows(min_row=1, max_row=1))]
    print("表头:", hdr)

if __name__ == "__main__":
    main()
