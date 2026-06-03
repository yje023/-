"""任务质检服务：错别字、逻辑、标点、重复任务检测"""
import re
from collections import defaultdict
from models import db, Task, QualityIssue, ConfirmedPattern, ProxyMetricPair, Unit, Organization
from sqlalchemy.orm import joinedload
import hashlib


def _task_to_row(t):
    """将 Task 对象转为检测引擎需要的 dict"""
    return {
        "file_path": f"unit_{t.unit_id or 0}",
        "folder": "",
        "unit_name": t.unit.name if t.unit else "",
        "unit_id": t.unit_id or 0,
        "sheet_row": t.id,
        "seq": t.id,
        "dimension": t.assessment_dimension.name if t.assessment_dimension else "",
        "eval_dept": t.assessor_unit.name if t.assessor_unit else "",
        "assessor_unit_id": t.assessor_unit_id or 0,
        "key_task": t.key_work or "",
        "main_task": t.main_task or "",
        "scoring_rule": t.scoring_note or "",
        "completion": "",
    }


def _hash_text(text):
    return hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()


def _load_confirmed_hashes(plan_id):
    """预加载指定方案下已确认的模式哈希，避免逐个查询数据库"""
    patterns = ConfirmedPattern.query.filter_by(plan_id=plan_id).all()
    return set((p.issue_type, p.text_hash) for p in patterns)


def _is_confirmed_pattern(issue, confirmed_hashes):
    """检查该问题是否已被确认无误（内存匹配）"""
    text = issue.get("text", "")
    if not text:
        return False
    return (issue["issue_type"], _hash_text(text)) in confirmed_hashes


def run_quality_check(plan_id=None):
    """对指定方案的任务执行全部 5 类检测，结果写入 DB"""
    q = Task.query.options(
        joinedload(Task.unit),
        joinedload(Task.assessment_dimension),
        joinedload(Task.assessor_unit),
    )
    if plan_id:
        q = q.filter(Task.plan_id == plan_id)
    q = q.order_by(Task.unit_id, Task.assessor_unit_id, Task.id)
    tasks = q.all()
    rows = [_task_to_row(t) for t in tasks]

    # 构建 unit_id → unit_type 映射（street=镇街一级单位, dept=部门）
    all_orgs = Organization.query.all()
    org_map = {o.id: o for o in all_orgs}
    street_org_ids = set()

    def _find_descendants(org_id):
        street_org_ids.add(org_id)
        for child_id, child in org_map.items():
            if child.parent_id == org_id:
                _find_descendants(child_id)

    street_root = next((o for o in all_orgs if o.name == "乡镇街道"), None)
    if street_root:
        _find_descendants(street_root.id)

    all_units = Unit.query.all()
    unit_type_map = {}
    for u in all_units:
        unit_type_map[u.id] = "street" if u.org_id in street_org_ids else "dept"

    for r in rows:
        r["unit_type"] = unit_type_map.get(r.get("unit_id"), "dept")
        r["assessor_unit_type"] = unit_type_map.get(r.get("assessor_unit_id"), "dept")

    # 清除该方案旧检测结果（仅清除 pending 状态）
    if plan_id:
        QualityIssue.query.filter_by(plan_id=plan_id, status="pending").delete(synchronize_session=False)

    confirmed_hashes = _load_confirmed_hashes(plan_id)

    existing_handled = set()
    if plan_id:
        handled_rows = db.session.query(
            QualityIssue.task_id, QualityIssue.issue_type,
            QualityIssue.column_name, QualityIssue.text,
        ).filter(
            QualityIssue.plan_id == plan_id,
            QualityIssue.status.in_(["confirmed", "resolved"]),
        ).all()
        for task_id, issue_type, col_name, text in handled_rows:
            existing_handled.add((task_id, issue_type, col_name or "", _hash_text(text or "")))

    saved_orm_objects = []
    excluded_by_confirmed = 0
    excluded_by_handled = 0

    def save_issues(issues_list):
        nonlocal excluded_by_confirmed, excluded_by_handled
        for iss in issues_list:
            if _is_confirmed_pattern(iss, confirmed_hashes):
                excluded_by_confirmed += 1
                continue
            iss_key = (
                iss.get("task_id"), iss["issue_type"],
                iss.get("column", ""), _hash_text(iss.get("text", "") or ""),
            )
            if iss_key in existing_handled:
                excluded_by_handled += 1
                continue
            qi = QualityIssue(
                plan_id=plan_id, task_id=iss.get("task_id"),
                issue_type=iss["issue_type"], column_name=iss.get("column", ""),
                text=iss.get("text", "")[:500], suggestion=iss.get("suggestion", "")[:500],
                context=iss.get("context", "")[:500],
                confidence=iss.get("confidence", "medium"), status="pending",
            )
            db.session.add(qi)
            saved_orm_objects.append((qi, iss))

    save_issues(_check_typos(rows))
    save_issues(_check_logic(rows))
    save_issues(_check_punctuation(rows))
    save_issues(_check_duplicates(rows))

    db.session.commit()

    # 疑似以指标考指标 — 同步到 ProxyMetricPair 表
    proxy_issues = _check_proxy_metrics(rows, plan_id=plan_id)
    added, updated, removed = _sync_proxy_pairs(plan_id, proxy_issues)

    row_map = {r["seq"]: r for r in rows}
    all_issues = []
    for qi, original in saved_orm_objects:
        item = dict(original)
        item["id"] = qi.id
        item["status"] = "pending"
        r = row_map.get(item.get("task_id"))
        if r:
            item["assessor_unit_name"] = r.get("eval_dept", "")
            item["main_task"] = r.get("main_task", "")
        all_issues.append(item)

    from collections import Counter
    type_counts = Counter(i["issue_type"] for i in all_issues)

    # 统计代理指标 pending 数量
    proxy_pending_count = ProxyMetricPair.query.filter_by(
        plan_id=plan_id, status="pending"
    ).count() if plan_id else len(proxy_issues)

    return {
        "total_tasks": len(tasks),
        "issues": all_issues,
        "summary": {
            "错别字": sum(v for k, v in type_counts.items() if "错别字" in k),
            "逻辑问题": sum(v for k, v in type_counts.items() if "逻辑" in k),
            "标点符号": sum(v for k, v in type_counts.items() if "标点" in k),
            "重复任务": sum(v for k, v in type_counts.items() if "重复" in k),
            "疑似以指标考指标": proxy_pending_count,
        },
        "total_issues": len(all_issues),
        "proxy_metric_count": proxy_pending_count,
        "proxy_sync": {"added": added, "updated": updated, "removed": removed},
        "excluded": {
            "by_confirmed_pattern": excluded_by_confirmed,
            "by_existing_handled": excluded_by_handled,
        },
    }

def get_proxy_issues(plan_id):
    """获取疑似以指标考指标问题（从 ProxyMetricPair 表读取）"""
    if not plan_id:
        return []

    pairs = ProxyMetricPair.query.filter_by(plan_id=plan_id).order_by(
        ProxyMetricPair.id
    ).all()

    result = []
    for pr in pairs:
        # 获取任务关联信息
        task_a = pr.task_a
        task_b = pr.task_b
        middle_unit = pr.middle_unit

        middle_unit_name = middle_unit.name if middle_unit else ""
        source_unit_name = task_a.assessor_unit.name if task_a and task_a.assessor_unit else ""
        target_unit_name = task_b.unit.name if task_b and task_b.unit else ""

        recv_kw = (task_a.key_work or "") if task_a else ""
        recv_mt = (task_a.main_task or "") if task_a else ""
        asgn_kw = (task_b.key_work or "") if task_b else ""
        asgn_mt = (task_b.main_task or "") if task_b else ""

        text_parts = []
        if recv_kw:
            text_parts.append(f"收到({source_unit_name}): {recv_kw[:60]}")
        if asgn_kw:
            text_parts.append(f"下发({target_unit_name}): {asgn_kw[:60]}")
        text = " | ".join(text_parts)

        suggestion = (
            f'"{source_unit_name}"以"{recv_kw[:40]}"下发至"{middle_unit_name}"，'
            f'"{middle_unit_name}"以相似任务"{asgn_kw[:40]}"下发至"{target_unit_name}"'
            f'（相似度{pr.similarity:.2f}），建议分解为具体操作事项'
        )

        result.append({
            "id": pr.id,
            "task_id": pr.task_id_a,
            "task_id_b": pr.task_id_b,
            "unit_name": middle_unit_name,
            "middle_unit_id": pr.middle_unit_id,
            "column": "重点工作/主要任务",
            "issue_type": "疑似以指标考指标",
            "text": text[:500],
            "suggestion": suggestion[:500],
            "context": f"{source_unit_name} -> {middle_unit_name} -> {target_unit_name}",
            "confidence": pr.confidence,
            "status": pr.status,
            "similarity": pr.similarity,
            "remark": pr.remark or "",
            "assessor_unit_name": source_unit_name,
            "main_task": recv_mt,
        })

    return result

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
    ("在次", "再次"), ("在来", "再来"), ("在说", "再说"), ("不在是", "不再是"),
    ("以经", "已经"), ("既使", "即使"), ("即然", "既然"), ("既便是", "即便是"),
    ("的却", "的确"), ("由其", "尤其"), ("不径而走", "不胫而走"), ("不加思索", "不假思索"),
    ("不落巢臼", "不落窠臼"), ("烩炙人口", "脍炙人口"), ("死皮懒脸", "死皮赖脸"),
    ("兰天白云", "蓝天白云"), ("顶力相助", "鼎力相助"), ("黄梁美梦", "黄粱美梦"),
    ("默守成规", "墨守成规"), ("一股作气", "一鼓作气"), ("悬梁刺骨", "悬梁刺股"),
    ("不记其数", "不计其数"), ("穿流不息", "川流不息"), ("别出新裁", "别出心裁"),
    ("汗流夹背", "汗流浃背"), ("迫不急待", "迫不及待"), ("原形必露", "原形毕露"),
    ("直接了当", "直截了当"), ("陈词烂调", "陈词滥调"), ("相辅相承", "相辅相成"),
    ("言简意该", "言简意赅"), ("自抱自弃", "自暴自弃"), ("出奇不意", "出其不意"),
    ("挺而走险", "铤而走险"), ("叹为观只", "叹为观止"), ("永往直前", "勇往直前"),
    ("仗义直言", "仗义执言"), ("张慌失措", "张皇失措"), ("指高气扬", "趾高气扬"),
    ("装腔作事", "装腔作势"), ("坐想其成", "坐享其成"), ("各行其事", "各行其是"),
    ("按步就班", "按部就班"), ("白壁微瑕", "白璧微瑕"), ("变本加利", "变本加厉"),
    ("病人膏肓", "病入膏肓"), ("不寒而粟", "不寒而栗"), ("不温不火", "不瘟不火"),
    ("苍海桑田", "沧海桑田"), ("草管人命", "草菅人命"), ("层峦迭嶂", "层峦叠嶂"),
    ("断章取意", "断章取义"), ("耳题面命", "耳提面命"), ("分道扬标", "分道扬镳"),
    ("鬼计多端", "诡计多端"), ("含辛如苦", "含辛茹苦"), ("集毁销骨", "积毁销骨"),
    ("娇揉造作", "矫揉造作"), ("金榜提名", "金榜题名"), ("既往不究", "既往不咎"),
    ("开门缉盗", "开门揖盗"), ("烂芋充数", "滥竽充数"), ("利害悠关", "利害攸关"),
    ("美轮美涣", "美轮美奂"), ("名落深山", "名落孙山"), ("明火执杖", "明火执仗"),
    ("莫不关心", "漠不关心"), ("磨肩接踵", "摩肩接踵"), ("旁证博引", "旁征博引"),
    ("其貌不祥", "其貌不扬"), ("气喘嘘嘘", "气喘吁吁"), ("千锤百练", "千锤百炼"),
    ("儒子可教", "孺子可教"), ("如法泡制", "如法炮制"), ("试目以待", "拭目以待"),
    ("一笔勾消", "一笔勾销"), ("一愁莫展", "一筹莫展"), ("一视同人", "一视同仁"),
    ("以逸代劳", "以逸待劳"), ("阴谋鬼计", "阴谋诡计"), ("余勇可估", "余勇可贾"),
    ("鱼目浑珠", "鱼目混珠"), ("语无论次", "语无伦次"), ("越俎代庖", "越俎代庖"),
    ("在劫难逃", "在劫难逃"), ("张冠李带", "张冠李戴"), ("真知卓见", "真知灼见"),
    ("自名不凡", "自命不凡"), ("走头无路", "走投无路"),
    ("恶耗", "噩耗"), ("幅射", "辐射"), ("技俩", "伎俩"), ("峻工", "竣工"),
    ("挛生", "孪生"), ("亲睐", "青睐"), ("痉孪", "痉挛"), ("迁灭", "歼灭"),
    ("通谍", "通牒"), ("弦律", "旋律"), ("脏款", "赃款"), ("九洲", "九州"),
    ("追朔", "追溯"), ("诵跃", "踊跃"), ("发韧", "发轫"), ("寒喧", "寒暄"),
    ("内哄", "内讧"), ("提练", "提炼"), ("通霄", "通宵"), ("弦晕", "眩晕"),
    ("婉惜", "惋惜"), ("嘻闹", "嬉闹"), ("消毁", "销毁"), ("隐密", "隐秘"),
    ("绉纹", "皱纹"), ("缈小", "渺小"), ("搭挡", "搭档"), ("担误", "耽误"),
    ("反覆", "反复"), ("烦脑", "烦恼"), ("防害", "妨害"), ("锋涌", "蜂拥"),
    ("复没", "覆没"), ("哽噎", "哽咽"), ("贯例", "惯例"), ("涵数", "函数"),
    ("号淘", "号啕"), ("宏扬", "弘扬"), ("慌恐", "惶恐"), ("汇演", "会演"),
    ("忌禁", "禁忌"), ("佳奖", "嘉奖"), ("驾御", "驾驭"), ("减默", "缄默"),
    ("娇宠", "骄宠"), ("骄艳", "娇艳"), ("缴文", "檄文"), ("介蒂", "芥蒂"),
    ("锦秀", "锦绣"), ("敬配", "敬佩"), ("咀咒", "诅咒"), ("峻岭", "峻岭"),
    ("开消", "开销"), ("扣门", "叩门"), ("苦脑", "苦恼"), ("烂用", "滥用"),
    ("老到", "老道"), ("雷庭", "雷霆"), ("脸夹", "脸颊"), ("了亮", "嘹亮"),
    ("另件", "零件"), ("拢络", "笼络"), ("掠奇", "猎奇"), ("轮郭", "轮廓"),
    ("卖买", "买卖"), ("萌牙", "萌芽"), ("免强", "勉强"), ("摸糊", "模糊"),
    ("目堵", "目睹"), ("年令", "年龄"), ("旁皇", "彷徨"), ("片断", "片段"),
    ("前题", "前提"), ("趋热", "趋势"), ("取蒂", "取缔"), ("缺限", "缺陷"),
    ("溶合", "融合"), ("融恰", "融洽"), ("善长", "擅长"), ("申张", "伸张"),
    ("生份", "身份"), ("实足", "十足"), ("署假", "暑假"), ("水蒸汽", "水蒸气"),
    ("颂经", "诵经"), ("题纲", "提纲"), ("天簌", "天籁"), ("天崖", "天涯"),
    ("通辑", "通缉"), ("唯持", "维持"), ("污陷", "诬陷"), ("嘻笑", "嬉笑"),
    ("下工夫", "下功夫"), ("显象管", "显像管"), ("相矩", "相距"), ("象样", "像样"),
    ("心菲", "心扉"), ("形像", "形象"), ("修练", "修炼"), ("一笔抹杀", "一笔抹煞"),
    ("一颗不振", "一蹶不振"), ("依仗", "倚仗"), ("忧默", "幽默"), ("有持无恐", "有恃无恐"),
    ("愚眛", "愚昧"), ("元全", "完全"), ("再接再励", "再接再厉"), ("扎记", "札记"),
    ("沾污", "玷污"), ("震憾", "震撼"), ("整救", "拯救"), ("正理", "整理"),
    ("置高点", "制高点"), ("忠真", "忠贞"), ("妆饰", "装饰"), ("追任", "追认"),
    ("准雀", "准确"), ("姿意", "恣意"), ("自翊", "自诩"), ("综色", "棕色"),
    ("奏效", "奏效"), ("尊从", "遵从"), ("做揖", "作揖"),
]

SHAPE_CONFUSIONS = [
    ("己", "已", ["已经", "已完成", "已整改", "已落实", "已制定"]),
    ("侯", "候", ["时候", "等候", "候选"]),
    ("既", "即", ["即使", "立即", "即刻"]),
    ("折", "拆", ["拆除", "拆迁", "拆分"]),
    ("人", "入", ["进入", "加入", "投入", "纳入", "录入"]),
    ("末", "未", ["未来", "未知", "未免", "未完成", "未达标"]),
    ("土", "士", ["人士", "战士", "勇士", "烈士"]),
    ("千", "干", ["干部", "干事", "干好", "干净"]),
    ("曰", "日", ["日期"]),
    ("天", "夫", ["功夫", "工夫", "丈夫"]),
    ("拨", "拔", ["选拔", "提拔", "拔尖"]),
    ("贷", "货", ["货物", "货源", "送货"]),
    ("徒", "徙", ["迁徙", "转徙"]),
    ("茶", "荼", ["荼毒"]),
    ("崇", "祟", ["作祟", "鬼祟"]),
    ("缀", "辍", ["辍学", "中辍"]),
    ("剌", "刺", ["刺客", "刺杀"]),
    ("欧", "殴", ["殴打", "斗殴"]),
    ("隐", "稳", ["稳定", "稳固", "稳中求进"]),
    ("历", "厉", ["厉害", "严厉"]),
    ("燥", "躁", ["急躁", "烦躁", "暴躁"]),
    ("辨", "辩", ["辩论", "辩护", "辩解"]),
    ("梁", "粱", ["高粱", "粱米"]),
    ("寇", "冠", ["冠军", "夺冠", "冠状"]),
    ("概", "慨", ["感慨", "慷慨"]),
    ("祥", "详", ["详细", "详情", "详尽"]),
    ("徒", "陡", ["陡坡", "陡峭"]),
    ("竞", "竟", ["竟然", "究竟"]),
    ("遂", "逐", ["逐渐", "逐步"]),
]

TEXT_COLS = ["key_task", "main_task", "scoring_rule"]
COL_LABELS = {"key_task": "重点工作", "main_task": "主要任务", "scoring_rule": "评分说明"}

_HOMOPHONE_INDEX = {}
for _w, _c in HOMOPHONE_CONFUSIONS:
    if _w not in _HOMOPHONE_INDEX or len(_w) > 1:
        _HOMOPHONE_INDEX[_w] = (_c, "high")

_SHAPE_INDEX = {}
for _ec, _cc, _tw_list in SHAPE_CONFUSIONS:
    for _tw in _tw_list:
        _wrong_tw = _tw.replace(_cc, _ec)
        _SHAPE_INDEX[_wrong_tw] = (_tw, f"{_ec}/{_cc}混淆", "medium")


def _check_typos(rows):
    issues = []
    for row in rows:
        for col in TEXT_COLS:
            text = row.get(col, "")
            if not text or len(text) < 3:
                continue
            col_name = COL_LABELS.get(col, col)
            for wrong, (correct, confidence) in _HOMOPHONE_INDEX.items():
                idx = text.find(wrong)
                if idx >= 0:
                    ctx = text[max(0, idx - 10):idx + len(wrong) + 10]
                    issues.append({
                        "task_id": row["seq"], "unit_name": row["unit_name"],
                        "column": col_name, "issue_type": "错别字-同音混淆",
                        "text": wrong, "suggestion": f'"{wrong}"应为"{correct}"',
                        "context": ctx, "confidence": confidence,
                    })
            for wrong_tw, (correct_tw, desc, confidence) in _SHAPE_INDEX.items():
                idx = text.find(wrong_tw)
                if idx >= 0:
                    ctx = text[max(0, idx - 10):idx + len(wrong_tw) + 10]
                    issues.append({
                        "task_id": row["seq"], "unit_name": row["unit_name"],
                        "column": col_name, "issue_type": "错别字-形近混淆",
                        "text": wrong_tw, "suggestion": f'"{wrong_tw}"应为"{correct_tw}"({desc})',
                        "context": ctx, "confidence": confidence,
                    })
            for m in re.finditer(r"(?<!\d)202[0-4](?!\d)", text):
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

            for m in re.finditer(r"(?<![0-9]),(?![0-9])", text):
                issues.append({
                    "task_id": row["seq"], "unit_name": row["unit_name"],
                    "column": col_name, "issue_type": "标点-英文逗号",
                    "text": text[max(0, m.start() - 5):m.end() + 5],
                    "suggestion": "建议改用中文逗号", "context": "", "confidence": "medium",
                })

            for m in re.finditer(r"\([^)]{2,}\)", text):
                inner = m.group()[1:-1]
                if _is_chinese_text(inner):
                    issues.append({
                        "task_id": row["seq"], "unit_name": row["unit_name"],
                        "column": col_name, "issue_type": "标点-英文括号",
                        "text": m.group()[:40], "suggestion": "建议改用中文括号（）",
                        "context": "", "confidence": "medium",
                    })

            stripped = text.strip()
            if len(stripped) > 30 and "，" in stripped:
                valid_ends = ("。", "！", "？", "…", "）", ")", "】", "》", "分")
                connecting_ends_tuple = ("，", "、", "；", "的", "了", "得", "着", "地", "不", "被", "把",
                                        "也", "在", "和", "与", "及", "或", "而", "但", "如", "需", "由",
                                        "可", "从", "到", "以", "按", "每")
                if not stripped.endswith(valid_ends) and stripped[-1] not in connecting_ends_tuple:
                    tail = stripped[-30:]
                    issues.append({
                        "task_id": row["seq"], "unit_name": row["unit_name"],
                        "column": col_name, "issue_type": "标点-缺少结尾",
                        "text": f"...{tail}", "suggestion": "文本缺少句号等结束标点",
                        "context": "", "confidence": "low",
                    })

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


def _char_ngrams_metric(text, n=2):
    """N-gram 清洗（指标类任务专用）—— 保留数字和%，去除标点噪声。"""
    clean = text.replace(" ", "").replace("\n", "").replace("\r", "")
    for ch in "、，。！？；：\"\"''《》【】…—":
        clean = clean.replace(ch, "")
    for ch in ".,!?;:()/-":
        clean = clean.replace(ch, "")
    if len(clean) < n:
        return set()
    return set(clean[i:i + n] for i in range(len(clean) - n + 1))


def _ngram_sim(ng1, ng2):
    """从预计算的 n-gram 集合直接计算 Jaccard"""
    if not ng1 or not ng2:
        return 0.0
    return len(ng1 & ng2) / len(ng1 | ng2)


def _unit_relation_desc(unit_a, unit_b):
    if unit_a == unit_b:
        return unit_a
    return f"{unit_a} ↔ {unit_b}"


def _check_duplicates(rows):
    """检测重复任务（全局比较，不限于同一被考核单位）

    视为重复的三种情况：
    1. 不同主考单位 → 不同被考核单位，任务相同或语义相似
    2. 不同主考单位 → 同一被考核单位，任务相同或语义相似
    3. 同一主考单位 → 同一被考核单位，任务相同或语义相似（录入错误）

    不视为重复：同一主考单位 → 不同被考核单位（模板复用）
    """
    if not rows:
        return []

    MAX_TASKS = 300
    sampled = rows
    if len(rows) > MAX_TASKS:
        unit_buckets = defaultdict(list)
        for i, r in enumerate(rows):
            unit_buckets[r["unit_name"]].append((i, r))
        sampled = []
        per_unit = max(1, MAX_TASKS // max(len(unit_buckets), 1))
        leftover = MAX_TASKS - per_unit * len(unit_buckets)
        for unit_name, bucket in unit_buckets.items():
            take = min(len(bucket), per_unit + (1 if leftover > 0 else 0))
            if leftover > 0: leftover -= 1
            step = max(1, len(bucket) // take)
            for k in range(0, len(bucket), step):
                sampled.append(bucket[k][1])
                if len(sampled) >= MAX_TASKS: break
            if len(sampled) >= MAX_TASKS: break
        sampled = sampled[:MAX_TASKS]

    n = len(sampled)
    precomputed = []
    for i in range(n):
        kw = sampled[i]["key_task"].strip()
        mt = sampled[i]["main_task"].strip()
        full = f"{kw} {mt}"
        precomputed.append({
            "idx": i, "dept": sampled[i]["eval_dept"],
            "unit_name": sampled[i]["unit_name"],
            "kw": kw, "mt": mt,
            "kw_ng": _char_ngrams(kw) if kw else set(),
            "mt_ng": _char_ngrams(mt) if mt else set(),
            "full_ng": _char_ngrams(full) if full else set(),
        })

    duplicates = []
    for i in range(n):
        pi = precomputed[i]
        for j in range(i + 1, n):
            pj = precomputed[j]
            # 同一主考单位给不同被考核单位分配相同/相似任务不视为重复
            if pi["dept"] == pj["dept"] and pi["unit_name"] != pj["unit_name"]:
                continue

            if pi["kw"] and pi["kw"] == pj["kw"]:
                main_sim = _ngram_sim(pi["mt_ng"], pj["mt_ng"])
                mt_min_len = min(len(pi["mt"]), len(pj["mt"]))
                mt_threshold = 0.10 if mt_min_len <= 15 else 0.15
                if main_sim < mt_threshold:
                    continue
                unit_desc = _unit_relation_desc(pi["unit_name"], pj["unit_name"])
                duplicates.append({
                    "task_id": sampled[pi["idx"]]["seq"],
                    "task_id_b": sampled[pj["idx"]]["seq"],
                    "unit_name": unit_desc,
                    "column": "重点工作/主要任务",
                    "issue_type": "重复任务-精确匹配",
                    "text": f'{pi["kw"][:30]} | {pi["mt"][:30]}',
                    "suggestion": f'"{pi["dept"]}"→"{pi["unit_name"]}" 与 "{pj["dept"]}"→"{pj["unit_name"]}" 分配了相同重点工作，主要任务也相似（相似度{main_sim:.2f}）',
                    "context": f'{pi["dept"]}→{pi["unit_name"]} ←→ {pj["dept"]}→{pj["unit_name"]}',
                    "confidence": "high" if main_sim >= 0.60 else "medium",
                    "similarity": round(main_sim, 3),
                })
                continue

            if abs(len(pi["kw"]) - len(pj["kw"])) > 10:
                continue

            key_sim = _ngram_sim(pi["kw_ng"], pj["kw_ng"])
            full_sim = _ngram_sim(pi["full_ng"], pj["full_ng"])
            main_sim = _ngram_sim(pi["mt_ng"], pj["mt_ng"])

            is_dup = full_sim >= 0.62 or (key_sim >= 0.72 and main_sim >= 0.10)
            if is_dup:
                sim_score = round(max(full_sim, key_sim), 3)
                unit_desc = _unit_relation_desc(pi["unit_name"], pj["unit_name"])
                duplicates.append({
                    "task_id": sampled[pi["idx"]]["seq"],
                    "task_id_b": sampled[pj["idx"]]["seq"],
                    "unit_name": unit_desc,
                    "column": "重点工作/主要任务",
                    "issue_type": "重复任务-语义相似",
                    "text": f'{pi["kw"][:30]} ≈ {pj["kw"][:30]}',
                    "suggestion": f'"{pi["dept"]}"→"{pi["unit_name"]}" 与 "{pj["dept"]}"→"{pj["unit_name"]}" 分配了相似任务（整体相似度{full_sim:.2f}）',
                    "context": f'{pi["dept"]}→{pi["unit_name"]} ←→ {pj["dept"]}→{pj["unit_name"]}',
                    "confidence": "medium",
                    "similarity": sim_score,
                })

    seen = set()
    unique = []
    for d in duplicates:
        key = (min(d.get("task_id", 0), d.get("task_id_b", 0)),
               max(d.get("task_id", 0), d.get("task_id_b", 0)))
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique[:500]


# ============ 5. 疑似以指标考指标检测 ============

def _check_proxy_metrics(rows, plan_id=None):
    """检测"疑似以指标考指标"：某单位收到含 % 的指标类任务后，
    转手给下级单位下发语义相似的指标类任务，未将指标拆解为具体工作。
    不入库、不计入问题总数。
    """
    if not rows:
        return []

    SIMILARITY_THRESHOLD = 0.20

    confirmed_pairs = set()
    if plan_id:
        # 从 ProxyMetricPair 表加载已确认/已修正/已忽略的 pair
        handled = ProxyMetricPair.query.filter(
            ProxyMetricPair.plan_id == plan_id,
            ProxyMetricPair.status.in_(["confirmed", "resolved", "ignored"]),
        ).all()
        for pr in handled:
            confirmed_pairs.add(f"{min(pr.task_id_a, pr.task_id_b)}:{max(pr.task_id_a, pr.task_id_b)}")

    metric_tasks = []
    for row in rows:
        kw = row.get("key_task", "") or ""
        mt = row.get("main_task", "") or ""
        if "%" in f"{kw} {mt}":
            metric_tasks.append(row)

    if len(metric_tasks) < 2:
        return []

    received_by_unit = defaultdict(list)
    assigned_by_unit = defaultdict(list)

    for row in metric_tasks:
        uid = row.get("unit_id")
        aid = row.get("assessor_unit_id")
        if uid: received_by_unit[uid].append(row)
        if aid: assigned_by_unit[aid].append(row)

    middle_units = set(received_by_unit.keys()) & set(assigned_by_unit.keys())
    if not middle_units:
        return []

    issues = []
    for unit_id in middle_units:
        recv_list = received_by_unit[unit_id]
        asgn_list = assigned_by_unit[unit_id]
        unit_name = recv_list[0].get("unit_name", "") if recv_list else ""

        recv_ngrams = []
        for recv in recv_list:
            text = f"{recv.get('key_task', '')} {recv.get('main_task', '')}".strip()
            recv_ngrams.append(_char_ngrams_metric(text))

        asgn_ngrams = []
        for asgn in asgn_list:
            text = f"{asgn.get('key_task', '')} {asgn.get('main_task', '')}".strip()
            asgn_ngrams.append(_char_ngrams_metric(text))

        for ri, recv in enumerate(recv_list):
            recv_ng = recv_ngrams[ri]
            if not recv_ng: continue
            source_unit = recv.get("eval_dept", "")
            recv_kw = recv.get("key_task", "") or ""

            for ai, asgn in enumerate(asgn_list):
                asgn_ng = asgn_ngrams[ai]
                if not asgn_ng: continue
                target_unit = asgn.get("unit_name", "")
                asgn_kw = asgn.get("key_task", "") or ""

                pair_key = f"{min(recv['seq'], asgn['seq'])}:{max(recv['seq'], asgn['seq'])}"
                if pair_key in confirmed_pairs: continue

                sim = _ngram_sim(recv_ng, asgn_ng)
                if sim >= SIMILARITY_THRESHOLD:
                    text_parts = []
                    if recv_kw: text_parts.append(f"收到({source_unit}): {recv_kw[:60]}")
                    if asgn_kw: text_parts.append(f"下发({target_unit}): {asgn_kw[:60]}")
                    text = " | ".join(text_parts)

                    issues.append({
                        "task_id": recv["seq"], "task_id_b": asgn["seq"],
                        "unit_name": unit_name,
                        "middle_unit_id": unit_id,
                        "column": "重点工作/主要任务",
                        "issue_type": "疑似以指标考指标",
                        "text": text[:500],
                        "suggestion": (
                            f'"{source_unit}"以"{recv_kw[:40]}"下发至"{unit_name}"，'
                            f'"{unit_name}"以相似任务"{asgn_kw[:40]}"下发至"{target_unit}"'
                            f'（相似度{sim:.2f}），建议分解为具体操作事项'
                        )[:500],
                        "context": f"{source_unit} -> {unit_name} -> {target_unit}",
                        "confidence": "high" if sim >= 0.35 else "medium",
                        "similarity": round(sim, 3),
                    })

    seen = set()
    unique = []
    for d in issues:
        key = (min(d["task_id"], d.get("task_id_b", 0)),
               max(d["task_id"], d.get("task_id_b", 0)))
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


def _sync_proxy_pairs(plan_id, detected_pairs):
    """将检测到的代理指标对同步到 ProxyMetricPair 表

    1. 新检测到的 pair → INSERT（status=pending）
    2. 已存在的 pending → UPDATE（更新 similarity）
    3. 旧的 pending 不在新结果中 → DELETE（任务已被修改，不再相似）
    4. confirmed/resolved/ignored 记录 → 保留不动
    """
    # 规范化检测结果的 key 集合
    detected_map = {}
    for p in detected_pairs:
        tid_a = p.get("task_id", 0)
        tid_b = p.get("task_id_b", 0)
        key = (min(tid_a, tid_b), max(tid_a, tid_b))
        detected_map[key] = p

    detected_keys = set(detected_map.keys())

    # 加载该方案下所有已有记录
    existing = ProxyMetricPair.query.filter_by(plan_id=plan_id).all()
    existing_map = {}
    for rec in existing:
        key = (min(rec.task_id_a, rec.task_id_b), max(rec.task_id_a, rec.task_id_b))
        existing_map[key] = rec

    existing_keys = set(existing_map.keys())

    # 新增：不在已有记录中的
    new_keys = detected_keys - existing_keys
    for key in new_keys:
        p = detected_map[key]
        tid_a, tid_b = key
        pr = ProxyMetricPair(
            plan_id=plan_id,
            task_id_a=tid_a,
            task_id_b=tid_b,
            middle_unit_id=p.get("middle_unit_id"),
            similarity=p.get("similarity", 0.0),
            confidence=p.get("confidence", "medium"),
            status="pending",
        )
        db.session.add(pr)

    # 更新：已有 pending 记录中的，更新 similarity
    pending_keys = {k for k, rec in existing_map.items() if rec.status == "pending"}
    update_keys = pending_keys & detected_keys
    for key in update_keys:
        p = detected_map[key]
        rec = existing_map[key]
        rec.similarity = p.get("similarity", rec.similarity)
        rec.confidence = p.get("confidence", rec.confidence)

    # 删除：旧的 pending 不在新结果中（任务已修改，不再相似）
    stale_keys = pending_keys - detected_keys
    for key in stale_keys:
        rec = existing_map[key]
        db.session.delete(rec)

    return len(new_keys), len(update_keys), len(stale_keys)
