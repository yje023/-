"""任务质检服务：错别字、逻辑、标点、重复任务检测"""
import re
from collections import defaultdict
from models import db, Task, QualityIssue, ConfirmedPattern
import hashlib


def _task_to_row(t):
    """将 Task 对象转为检测引擎需要的 dict"""
    return {
        "file_path": f"unit_{t.unit_id or 0}",
        "folder": "",
        "unit_name": t.unit.name if t.unit else "",
        "sheet_row": t.id,
        "seq": t.id,
        "dimension": t.assessment_dimension.name if t.assessment_dimension else "",
        "eval_dept": t.assessor_unit.name if t.assessor_unit else "",
        "key_task": t.key_work or "",
        "main_task": t.main_task or "",
        "scoring_rule": t.scoring_note or "",
        "completion": "",
    }


def _hash_text(text):
    return hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()


def _is_confirmed_pattern(issue):
    """检查该问题是否已被确认无误（同类型+同文本）"""
    text = issue.get("text", "")
    if not text:
        return False
    h = _hash_text(text)
    return ConfirmedPattern.query.filter_by(issue_type=issue["issue_type"], text_hash=h).first() is not None


def run_quality_check(plan_id=None):
    """对指定方案的任务执行全部 4 类检测，结果写入 DB"""
    q = Task.query
    if plan_id:
        q = q.filter(Task.plan_id == plan_id)
    tasks = q.all()
    rows = [_task_to_row(t) for t in tasks]

    # 清除该方案旧检测结果（仅清除 pending 状态）
    if plan_id:
        QualityIssue.query.filter_by(plan_id=plan_id, status="pending").delete()

    all_issues = []

    def save_issues(issues_list):
        for iss in issues_list:
            # 跳过已确认无误的模式
            if _is_confirmed_pattern(iss):
                continue
            qi = QualityIssue(
                plan_id=plan_id,
                task_id=iss.get("task_id"),
                issue_type=iss["issue_type"],
                column_name=iss.get("column", ""),
                text=iss.get("text", "")[:500],
                suggestion=iss.get("suggestion", "")[:500],
                context=iss.get("context", "")[:500],
                confidence=iss.get("confidence", "medium"),
                status="pending",
            )
            db.session.add(qi)
        all_issues.extend(issues_list)

    # 1-3: 单任务检测
    save_issues(_check_typos(rows))
    save_issues(_check_logic(rows))
    save_issues(_check_punctuation(rows))

    # 4: 重复检测
    dups = _check_duplicates(rows)
    all_issues.extend(dups)

    db.session.commit()

    # 统计
    from collections import Counter
    type_counts = Counter(i["issue_type"] for i in all_issues)

    return {
        "total_tasks": len(tasks),
        "issues": all_issues,
        "summary": {
            "错别字": sum(1 for k, v in type_counts.items() if "错别字" in k),
            "逻辑问题": sum(1 for k, v in type_counts.items() if "逻辑" in k),
            "标点符号": sum(1 for k, v in type_counts.items() if "标点" in k),
            "重复任务": sum(1 for k, v in type_counts.items() if "重复" in k),
        },
        "total_issues": len(all_issues),
    }


# ============ 1. 错别字检测 ============

HOMOPHONE_CONFUSIONS = [
    ("布署", "部署"), ("按排", "安排"), ("耽误差", "耽误"), ("赋于", "赋予"),
    ("其它", "其他"), ("做为", "作为"), ("必需", "必须"), ("截止", "截至"),
    ("帐户", "账户"), ("联接", "连接"), ("图象", "图像"), ("惟一", "唯一"),
    ("部份", "部分"), ("签定", "签订"), ("辩别", "辨别"), ("车箱", "车厢"),
    ("沉绽", "沉淀"), ("凑和", "凑合"), ("抵压", "抵押"), ("过余", "过于"),
    ("好象", "好像"), ("决对", "绝对"), ("克苦", "刻苦"), ("另售", "零售"),
    ("脉博", "脉搏"), ("膨涨", "膨胀"), ("频临", "濒临"), ("凭添", "平添"),
    ("气慨", "气概"), ("迁徒", "迁徙"), ("搔扰", "骚扰"), ("杀戳", "杀戮"),
    ("霎那", "刹那"), ("世外桃园", "世外桃源"), ("欣尝", "欣赏"), ("渲泄", "宣泄"),
    ("寻问", "询问"), ("夜霄", "夜宵"), ("一柱香", "一炷香"), ("膺品", "赝品"),
    ("震奋", "振奋"), ("坐阵", "坐镇"), ("记念", "纪念"), ("规化", "规划"),
    ("牵联", "牵连"), ("关健", "关键"), ("决择", "抉择"), ("报怨", "抱怨"),
    ("得已", "得以"), ("恶梦", "噩梦"), ("法码", "砝码"), ("防碍", "妨碍"),
    ("份量", "分量"), ("复盖", "覆盖"), ("干予", "干预"), ("函养", "涵养"),
    ("耗废", "耗费"), ("即然", "既然"), ("陷井", "陷阱"), ("具大", "巨大"),
    ("了望", "瞭望"), ("流览", "浏览"), ("麻疯", "麻风"), ("迷底", "谜底"),
    ("篷勃", "蓬勃"), ("偏面", "片面"), ("迁就", "牵就"), ("顷诉", "倾诉"),
    ("收迄", "收讫"), ("污告", "诬告"), ("义气", "意气"), ("造形", "造型"),
    ("真缔", "真谛"), ("尊循", "遵循"), ("坐位", "座位"), ("澳州", "澳洲"),
]

SHAPE_CONFUSIONS = [
    ("己", "已", ["已经", "已完成", "已整改", "已落实", "已制定"]),
    ("侯", "候", ["时候", "等候", "候选"]),
    ("即", "既", ["即使", "立即", "即刻"]),
    ("折", "拆", ["拆除", "拆迁", "拆分"]),
]

TEXT_COLS = ["key_task", "main_task", "scoring_rule"]
COL_LABELS = {"key_task": "重点工作", "main_task": "主要任务", "scoring_rule": "评分说明"}


def _check_typos(rows):
    issues = []
    for row in rows:
        for col in TEXT_COLS:
            text = row.get(col, "")
            if not text or len(text) < 3:
                continue
            col_name = COL_LABELS.get(col, col)

            # 同音字
            for wrong, correct in HOMOPHONE_CONFUSIONS:
                if wrong in text:
                    idx = text.find(wrong)
                    ctx = text[max(0, idx - 10):idx + len(wrong) + 10]
                    issues.append({
                        "task_id": row["seq"], "unit_name": row["unit_name"],
                        "column": col_name, "issue_type": "错别字-同音混淆",
                        "text": wrong, "suggestion": f'"{wrong}"应为"{correct}"',
                        "context": ctx, "confidence": "high",
                    })

            # 形近字
            for error_char, correct_char, triggers in SHAPE_CONFUSIONS:
                if error_char not in text:
                    continue
                for tw in triggers:
                    wrong_tw = tw.replace(correct_char, error_char)
                    if wrong_tw in text:
                        idx = text.find(wrong_tw)
                        ctx = text[max(0, idx - 10):idx + len(wrong_tw) + 10]
                        issues.append({
                            "task_id": row["seq"], "unit_name": row["unit_name"],
                            "column": col_name, "issue_type": "错别字-形近混淆",
                            "text": wrong_tw, "suggestion": f'"{wrong_tw}"应为"{tw}"({error_char}/{correct_char}混淆)',
                            "context": ctx, "confidence": "medium",
                        })

            # 年份异常
            for m in re.finditer(r"202[0-4]\d", text):
                issues.append({
                    "task_id": row["seq"], "unit_name": row["unit_name"],
                    "column": col_name, "issue_type": "错别字-数字异常",
                    "text": m.group(), "suggestion": "疑似年份错误，可能应为2025或2026",
                    "context": text[max(0, m.start() - 15):m.end() + 15], "confidence": "medium",
                })

    return issues


# ============ 2. 逻辑检测 ============

def _check_logic(rows):
    issues = []
    for row in rows:
        for col in ["main_task", "scoring_rule"]:
            text = row.get(col, "")
            if not text or len(text) < 5:
                continue
            col_name = COL_LABELS.get(col, col)

            # 编号格式不一致
            num_dot = re.findall(r"(?:^|\n)\s*(\d+)\.", text)
            num_dunhao = re.findall(r"(?:^|\n)\s*(\d+)、", text)
            num_cn = re.findall(r"（(\d+)）", text)
            num_en = re.findall(r"\((\d+)\)", text)
            styles = []
            if num_dot: styles.append("数字.")
            if num_dunhao: styles.append("数字、")
            if num_cn: styles.append("（数字）")
            if num_en: styles.append("(数字)")
            if len(styles) > 1:
                issues.append({
                    "task_id": row["seq"], "unit_name": row["unit_name"],
                    "column": col_name, "issue_type": "逻辑-编号混用",
                    "text": f'混用: {",".join(styles)}', "suggestion": "建议统一编号格式",
                    "context": text[:100], "confidence": "medium",
                })

            # 矛盾计分条件
            if col_name == "评分说明":
                for pat, desc in [
                    (r"不扣分.*?(?:但|然而|却|除).*?扣\d+", "不扣分后出现扣分条件"),
                    (r"满分.*?(?:但|然而|除).*?扣\d+", "满分后出现扣分项"),
                ]:
                    m = re.search(pat, text)
                    if m:
                        issues.append({
                            "task_id": row["seq"], "unit_name": row["unit_name"],
                            "column": col_name, "issue_type": "逻辑-计分矛盾",
                            "text": m.group()[:60], "suggestion": desc,
                            "context": text[max(0, m.start() - 10):m.end() + 10], "confidence": "medium",
                        })

            # 文本截断
            text_stripped = text.strip()
            valid_ends = ("。", "！", "？", "…", "）", ")", '"', '"', "】", "》", "分", "%", "人")
            connecting_ends = ("，", "、", "；", "的", "了", "得", "着", "地", "不", "被", "把",
                               "也", "在", "和", "与", "及", "或", "而", "但", "如", "需", "由",
                               "可", "从", "到", "以", "按", "每")
            if len(text_stripped) > 20 and not text_stripped.endswith(valid_ends) and text_stripped[-1] in connecting_ends:
                tail = text_stripped[-40:]
                issues.append({
                    "task_id": row["seq"], "unit_name": row["unit_name"],
                    "column": col_name, "issue_type": "逻辑-文本截断",
                    "text": f"...{tail}", "suggestion": "文本以连接词结尾，可能被截断",
                    "context": tail, "confidence": "low",
                })

            # 模糊量词
            for word in ["若干", "等等", "适当", "酌情", "视情况", "必要时", "原则上"]:
                if word in text:
                    idx = text.find(word)
                    issues.append({
                        "task_id": row["seq"], "unit_name": row["unit_name"],
                        "column": col_name, "issue_type": "逻辑-模糊表述",
                        "text": text[max(0, idx - 5):idx + len(word) + 5],
                        "suggestion": f'"{word}"为模糊量词，建议明确具体标准',
                        "context": text[max(0, idx - 15):idx + len(word) + 15], "confidence": "low",
                    })

    return issues


# ============ 3. 标点检测 ============

def _is_chinese_text(text):
    if not text: return False
    chinese = sum(1 for c in text if "一" <= c <= "鿿" or "　" <= c <= "〿")
    return chinese / max(len(text), 1) > 0.4


def _check_punctuation(rows):
    issues = []
    for row in rows:
        for col in TEXT_COLS:
            text = row.get(col, "")
            if not text or len(text) < 5:
                continue
            col_name = COL_LABELS.get(col, col)

            if not _is_chinese_text(text):
                continue

            # 英文逗号
            for m in re.finditer(r"(?<![0-9]),(?![0-9])", text):
                issues.append({
                    "task_id": row["seq"], "unit_name": row["unit_name"],
                    "column": col_name, "issue_type": "标点-英文逗号",
                    "text": text[max(0, m.start() - 5):m.end() + 5],
                    "suggestion": "建议改用中文逗号，", "context": "", "confidence": "medium",
                })

            # 英文括号
            for m in re.finditer(r"\([^)]{2,}\)", text):
                inner = m.group()[1:-1]
                if _is_chinese_text(inner):
                    issues.append({
                        "task_id": row["seq"], "unit_name": row["unit_name"],
                        "column": col_name, "issue_type": "标点-英文括号",
                        "text": m.group()[:40], "suggestion": "建议改用中文括号（）",
                        "context": "", "confidence": "medium",
                    })

            # 缺少结尾标点
            stripped = text.strip()
            if len(stripped) > 30 and "，" in stripped:
                valid_ends = ("。", "！", "？", "…", "）", ")", "】", "》", "分")
                if not stripped.endswith(valid_ends):
                    tail = stripped[-30:]
                    issues.append({
                        "task_id": row["seq"], "unit_name": row["unit_name"],
                        "column": col_name, "issue_type": "标点-缺少结尾",
                        "text": f"...{tail}", "suggestion": "文本缺少句号等结束标点",
                        "context": "", "confidence": "low",
                    })

            # 括号不配对
            for left, right, name in [("（", "）", "中文圆括号"), ("《", "》", "书名号"), ("【", "】", "方头括号")]:
                cl = text.count(left)
                cr = text.count(right)
                if cl != cr:
                    issues.append({
                        "task_id": row["seq"], "unit_name": row["unit_name"],
                        "column": col_name, "issue_type": "标点-括号不配对",
                        "text": f'左{left}×{cl} 右{right}×{cr}',
                        "suggestion": f"请检查{name}是否配对", "context": "", "confidence": "high",
                    })

    return issues


# ============ 4. 重复任务检测 ============

def _char_ngrams(text, n=2):
    clean = text.replace(" ", "").replace("\n", "")
    for ch in "（）()1234567890.":
        clean = clean.replace(ch, "")
    if len(clean) < n:
        return set()
    return set(clean[i:i + n] for i in range(len(clean) - n + 1))


def _jaccard_sim(t1, t2, n=2):
    ng1 = _char_ngrams(t1, n)
    ng2 = _char_ngrams(t2, n)
    if not ng1 or not ng2:
        return 0.0
    return len(ng1 & ng2) / len(ng1 | ng2)


def _check_duplicates(rows):
    """检测同一被考核单位下，不同评价部门分配相同或相似任务"""
    # 按 unit_name 分组
    unit_groups = defaultdict(list)
    for row in rows:
        unit_groups[row["unit_name"]].append(row)

    duplicates = []
    for unit_name, group in unit_groups.items():
        n = len(group)
        for i in range(n):
            for j in range(i + 1, n):
                dept_a = group[i]["eval_dept"]
                dept_b = group[j]["eval_dept"]
                if dept_a == dept_b:
                    continue

                kw_a = group[i]["key_task"].strip()
                kw_b = group[j]["key_task"].strip()

                # 精确匹配
                if kw_a and kw_a == kw_b:
                    duplicates.append({
                        "task_id": group[i]["seq"], "task_id_b": group[j]["seq"],
                        "unit_name": unit_name, "column": "重点工作",
                        "issue_type": "重复任务-精确匹配",
                        "text": kw_a,
                        "suggestion": f'"{dept_a}"和"{dept_b}"分配了相同重点工作',
                        "context": f'{dept_a} ←→ {dept_b}', "confidence": "high",
                        "similarity": 1.0,
                    })
                    continue

                # 语义相似
                full_a = f"{kw_a} {group[i]['main_task'].strip()}"
                full_b = f"{kw_b} {group[j]['main_task'].strip()}"
                key_sim = _jaccard_sim(kw_a, kw_b)
                full_sim = _jaccard_sim(full_a, full_b)
                if key_sim >= 0.72 or full_sim >= 0.68:
                    duplicates.append({
                        "task_id": group[i]["seq"], "task_id_b": group[j]["seq"],
                        "unit_name": unit_name, "column": "重点工作/主要任务",
                        "issue_type": "重复任务-语义相似",
                        "text": f'{kw_a[:30]} ≈ {kw_b[:30]}',
                        "suggestion": f'"{dept_a}"和"{dept_b}"分配了相似任务',
                        "context": f'{dept_a} ←→ {dept_b}', "confidence": "medium",
                        "similarity": round(max(key_sim, full_sim), 3),
                    })

    # 去重限制
    seen = set()
    unique = []
    for d in duplicates:
        key = (min(d.get("task_id", 0), d.get("task_id_b", 0)),
               max(d.get("task_id", 0), d.get("task_id_b", 0)))
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique[:500]
