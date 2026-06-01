import io, re, zipfile
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, Task, TaskSubmission, TaskScore, Plan, AssessmentDimension, Unit
from utils.xlsx_handler import export_xlsx, export_gov_xlsx, read_workbook, fuzzy_match_headers, HEADER_KEYWORDS

task_bp = Blueprint("task", __name__)


def _get_user(user_id):
    from models import User
    return User.query.get(user_id)


@task_bp.route("/api/tasks", methods=["GET"])
@jwt_required()
def list_tasks():
    user = _get_user(int(get_jwt_identity()))
    plan_id = request.args.get("plan_id", type=int)
    status = request.args.get("status", "").strip()
    search = request.args.get("search", "").strip()
    search_type = request.args.get("search_type", "all").strip()
    assessor_unit_id = request.args.get("assessor_unit_id", type=int)
    unit_id = request.args.get("unit_id", type=int)
    dimension_ids = request.args.get("dimension_ids", "").strip()
    key_works = request.args.get("key_works", "").strip()
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    page_size = min(page_size, 200)

    q = Task.query
    if plan_id:
        q = q.filter(Task.plan_id == plan_id)
    if status:
        q = q.filter(Task.status == status)
    if assessor_unit_id:
        ids = [int(x) for x in str(assessor_unit_id).split(",") if x.strip().isdigit()]
        if ids:
            q = q.filter(Task.assessor_unit_id.in_(ids))
    if unit_id:
        ids = [int(x) for x in str(unit_id).split(",") if x.strip().isdigit()]
        if ids:
            q = q.filter(Task.unit_id.in_(ids))
    if dimension_ids:
        ids = [int(x) for x in dimension_ids.split(",") if x.strip().isdigit()]
        if ids:
            q = q.filter(Task.assessment_dimension_id.in_(ids))
    if key_works:
        kws = [x.strip() for x in key_works.split(",") if x.strip()]
        if kws:
            conditions = [Task.key_work.contains(kw) for kw in kws]
            q = q.filter(db.or_(*conditions))
    if search:
        if search_type == "key_work":
            q = q.filter(Task.key_work.contains(search))
        elif search_type == "main_task":
            q = q.filter(Task.main_task.contains(search))
        elif search_type == "dimension":
            q = q.join(AssessmentDimension, Task.assessment_dimension_id == AssessmentDimension.id)\
                 .filter(AssessmentDimension.name.contains(search))
        elif search_type == "assessor":
            q = q.join(Unit, Task.assessor_unit_id == Unit.id)\
                 .filter(Unit.name.contains(search))
        elif search_type == "unit":
            q = q.join(Unit, Task.unit_id == Unit.id)\
                 .filter(Unit.name.contains(search))
        elif search_type == "period":
            q = q.filter(Task.review_period.contains(search))
        else:  # all
            q = q.filter(
                db.or_(
                    Task.key_work.contains(search),
                    Task.main_task.contains(search),
                    Task.scoring_note.contains(search),
                )
            )

    # 发布单位(系统管理员)看全部；被考核单位只看自己的；主考单位看评价部门是自己的
    is_publisher = user and user.role and user.role.is_system
    if not is_publisher:
        if user and user.current_identity == "assessed":
            q = q.filter(Task.unit_id == user.unit_id)
        elif user and user.current_identity == "assessor":
            q = q.filter(Task.assessor_unit_id == user.unit_id)

    total = q.count()
    tasks = q.order_by(Task.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    data = [_task_to_dict(t) for t in tasks]
    return jsonify({"data": {"items": data, "total": total, "page": page, "page_size": page_size}})


@task_bp.route("/api/tasks/filter-options", methods=["GET"])
@jwt_required()
def filter_options():
    """返回当前方案下可筛选的维度、重点工作、评价部门、被考核单位"""
    user = _get_user(int(get_jwt_identity()))
    plan_id = request.args.get("plan_id", type=int)

    q = Task.query
    if plan_id:
        q = q.filter(Task.plan_id == plan_id)

    # 权限过滤
    is_publisher = user and user.role and user.role.is_system
    if not is_publisher:
        if user and user.current_identity == "assessed":
            q = q.filter(Task.unit_id == user.unit_id)
        elif user and user.current_identity == "assessor":
            q = q.filter(Task.assessor_unit_id == user.unit_id)

    # 获取该查询条件下涉及的所有 task id
    task_ids = [t[0] for t in q.with_entities(Task.id).all()]
    if not task_ids:
        return jsonify({"data": {"dimensions": [], "key_works": [], "assessor_units": [], "assessed_units": []}})

    # 考核维度选项：从这些 task 中提取不重复的维度
    dims = (
        db.session.query(AssessmentDimension.id, AssessmentDimension.name)
        .join(Task, Task.assessment_dimension_id == AssessmentDimension.id)
        .filter(Task.id.in_(task_ids))
        .distinct().order_by(AssessmentDimension.name).all()
    )
    dimensions = [{"id": d[0], "name": d[1]} for d in dims]

    # 重点工作选项
    kws = (
        db.session.query(Task.key_work)
        .filter(Task.id.in_(task_ids), Task.key_work.isnot(None), Task.key_work != "")
        .distinct().order_by(Task.key_work).all()
    )
    key_works = [k[0] for k in kws if k[0]]

    # 评价部门选项
    assessors = (
        db.session.query(Unit.id, Unit.name)
        .join(Task, Task.assessor_unit_id == Unit.id)
        .filter(Task.id.in_(task_ids))
        .distinct().order_by(Unit.name).all()
    )
    assessor_units = [{"id": a[0], "name": a[1]} for a in assessors]

    # 被考核单位选项
    assessed = (
        db.session.query(Unit.id, Unit.name)
        .join(Task, Task.unit_id == Unit.id)
        .filter(Task.id.in_(task_ids))
        .distinct().order_by(Unit.name).all()
    )
    assessed_units = [{"id": u[0], "name": u[1]} for u in assessed]

    return jsonify({"data": {
        "dimensions": dimensions,
        "key_works": key_works,
        "assessor_units": assessor_units,
        "assessed_units": assessed_units,
    }})


def _task_to_dict(t):
    return {
        "id": t.id,
        "plan_id": t.plan_id,
        "assessment_dimension_id": t.assessment_dimension_id,
        "dimension_name": t.assessment_dimension.name if t.assessment_dimension else "未分配",
        "unit_id": t.unit_id,
        "unit_name": t.unit.name if t.unit else "未分配",
        "assessor_unit_id": t.assessor_unit_id,
        "assessor_unit_name": t.assessor_unit.name if t.assessor_unit else "未分配",
        "key_work": t.key_work,
        "main_task": t.main_task,
        "scoring_note": t.scoring_note or "",
        "review_period": t.review_period,
        "status": t.status,
        "submissions": [{"id": s.id, "content": s.content, "submitted_at": str(s.submitted_at)} for s in t.submissions],
        "scores": [{"id": s.id, "score": s.score, "comment": s.comment or "", "scored_at": str(s.scored_at)} for s in t.scores],
        "created_at": str(t.created_at),
    }


@task_bp.route("/api/tasks", methods=["POST"])
@jwt_required()
def create_task():
    data = request.get_json()
    required = ["plan_id", "assessment_dimension_id", "unit_id", "assessor_unit_id", "key_work", "main_task", "review_period"]
    for k in required:
        if not data.get(k):
            return jsonify({"msg": f"缺少必填项：{k}"}), 400

    task = Task(
        plan_id=data["plan_id"],
        assessment_dimension_id=data["assessment_dimension_id"],
        unit_id=data["unit_id"],
        assessor_unit_id=data["assessor_unit_id"],
        key_work=data["key_work"].strip(),
        main_task=data["main_task"].strip(),
        scoring_note=data.get("scoring_note", "").strip(),
        review_period=data["review_period"],
    )
    db.session.add(task)
    db.session.commit()
    return jsonify({"msg": "创建成功", "data": {"id": task.id}})


@task_bp.route("/api/tasks/<int:task_id>", methods=["PUT"])
@jwt_required()
def update_task(task_id):
    task = Task.query.get(task_id)
    if not task:
        return jsonify({"msg": "任务不存在"}), 404

    data = request.get_json()
    for field in ["key_work", "main_task", "scoring_note", "review_period"]:
        if data.get(field):
            setattr(task, field, data[field].strip())
    if data.get("assessment_dimension_id"):
        task.assessment_dimension_id = data["assessment_dimension_id"]
    if data.get("assessor_unit_id"):
        task.assessor_unit_id = data["assessor_unit_id"]

    db.session.commit()
    return jsonify({"msg": "编辑成功"})


@task_bp.route("/api/tasks/<int:task_id>", methods=["DELETE"])
@jwt_required()
def delete_task(task_id):
    task = Task.query.get(task_id)
    if not task:
        return jsonify({"msg": "任务不存在"}), 404
    db.session.delete(task)
    db.session.commit()
    return jsonify({"msg": "删除成功"})


@task_bp.route("/api/tasks/batch-all", methods=["DELETE"])
@jwt_required()
def batch_delete_all_tasks():
    """删除指定方案的全部考核任务"""
    plan_id = request.args.get("plan_id", type=int)
    q = Task.query
    if plan_id:
        q = q.filter_by(plan_id=plan_id)
    count = q.count()
    if count == 0:
        return jsonify({"msg": "没有可删除的任务"}), 200
    q.delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"msg": f"成功删除 {count} 个任务", "data": {"deleted": count}})


@task_bp.route("/api/tasks/<int:task_id>/review", methods=["PUT"])
@jwt_required()
def review_task(task_id):
    task = Task.query.get(task_id)
    if not task:
        return jsonify({"msg": "任务不存在"}), 404
    data = request.get_json()
    task.status = data.get("status", "reviewed")
    db.session.commit()
    return jsonify({"msg": "审核完成"})


# ==================== 填报打分 ====================

@task_bp.route("/api/tasks/<int:task_id>/submit", methods=["POST"])
@jwt_required()
def submit_task(task_id):
    task = Task.query.get(task_id)
    if not task:
        return jsonify({"msg": "任务不存在"}), 404

    user = _get_user(int(get_jwt_identity()))
    if user.unit_id != task.unit_id:
        return jsonify({"msg": "仅被考核单位可填报"}), 403

    data = request.get_json()
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"msg": "填报内容不能为空"}), 400

    submission = TaskSubmission(task_id=task.id, content=content)
    db.session.add(submission)
    task.status = "submitted"
    db.session.commit()
    return jsonify({"msg": "提交成功"})


@task_bp.route("/api/tasks/<int:task_id>/score", methods=["POST"])
@jwt_required()
def score_task(task_id):
    task = Task.query.get(task_id)
    if not task:
        return jsonify({"msg": "任务不存在"}), 404

    user = _get_user(int(get_jwt_identity()))
    if user.unit_id != task.assessor_unit_id:
        return jsonify({"msg": "仅评价部门可打分"}), 403

    data = request.get_json()
    score_val = data.get("score")
    if score_val is None:
        return jsonify({"msg": "分数不能为空"}), 400

    existing = TaskScore.query.filter_by(task_id=task.id).first()
    if existing:
        existing.score = float(score_val)
        existing.comment = data.get("comment", "").strip()
    else:
        db.session.add(TaskScore(task_id=task.id, score=float(score_val), comment=data.get("comment", "").strip()))

    task.status = "reviewed"
    db.session.commit()
    return jsonify({"msg": "打分成功"})


# ==================== 批量导入 ====================

# 需要跳过的工作表名称关键词
SKIP_SHEET_KEYWORDS = ["说明", "备注", "目录", "汇总", "统计", "Sheet", "sheet"]

# 模糊匹配所需的字段映射（与 HEADER_KEYWORDS 对应的字段列表）
IMPORT_FIELDS = ["seq", "unit", "dimension", "assessor", "key_work", "main_task", "scoring_note", "period"]


def _should_skip_sheet(sname):
    """判断是否应跳过该工作表"""
    for kw in SKIP_SHEET_KEYWORDS:
        if kw in sname:
            return True
    return False


def _normalize_name(name):
    """名称规范化：去除各类引号、空格等干扰字符"""
    if not name:
        return name
    result = []
    for ch in name:
        cp = ord(ch)
        # 去除 ASCII 引号、中文引号、全角括号：34=" 39=' 40=( 41=)
        # 8220=左双引号 8221=右双引号 8216=左单引号 8217=右单引号
        # 65282=全角引号 65288=（ 65289=）
        # 12300=「 12301=」 12302=『 12303=』 12298=《 12299=》 12304=【 12305=】
        if cp in (34, 39, 40, 41,
                  8220, 8221, 8216, 8217,
                  65282, 65288, 65289,
                  12300, 12301, 12302, 12303,
                  12298, 12299, 12304, 12305):
            continue
        result.append(ch)
    return ''.join(result).strip()

def _find_unit_in_set(name, unit_dict):
    """在方案预设单位集合中查找：精确匹配 → 模糊匹配降级"""
    name = _normalize_name(name)
    for uid, unit in unit_dict.items():
        if _normalize_name(unit.name) == name:
            return unit, None
    candidates = [u for u in unit_dict.values() if name in _normalize_name(u.name)]
    if len(candidates) == 1:
        return candidates[0], None
    elif len(candidates) > 1:
        return None, f"单位名称「{name}」匹配到多个：{', '.join(u.name for u in candidates[:5])}"
    candidates = [u for u in unit_dict.values() if name.replace('区', '') in _normalize_name(u.name)]
    if len(candidates) == 1:
        return candidates[0], None
    return None, f"单位「{name}」不在方案预设中"


def _find_dim_in_set(name, dim_dict):
    """在方案预设维度集合中查找：精确匹配 → 模糊匹配降级"""
    name = _normalize_name(name)
    for did, dim in dim_dict.items():
        if _normalize_name(dim.name) == name:
            return dim, None
    candidates = [d for d in dim_dict.values() if name in _normalize_name(d.name)]
    if len(candidates) == 1:
        return candidates[0], None
    return None, f"考核维度「{name}」不在方案预设中"


def _normalize_period(value):
    """标准化晾晒周期"""
    v = value.strip() if value else ""
    mapping = {
        "月": "月度", "月度": "月度", "monthly": "月度",
        "季": "季度", "季度": "季度", "quarterly": "季度",
        "半年": "半年度", "半年度": "半年度", "semiannual": "半年度",
        "年": "年度", "年度": "年度", "annual": "年度",
    }
    return mapping.get(v, v or "月度")


def _split_numbered_items(text):
    """将含编号列表的文本（如 '1. xxx\\n2. yyy'）拆分为独立条目。
    返回 (items_list, was_split)。无编号时返回 ([text], False)。"""
    if not text or not text.strip():
        return [text or ""], False
    t = text.strip()
    pattern = re.compile(r"(?:^|\n)\s*(\d+)\s*[\.、．\)）]\s*")
    matches = list(pattern.finditer(t))
    if len(matches) < 2:
        return [t], False
    items = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(t)
        content = t[start:end].strip()
        if content:
            items.append(content)
    if len(items) >= 2:
        return items, True
    return [t], False


def _expand_category_units(unit_name, plan_assessed_groups):
    """将类别关键词（如 '30个乡镇街道'）展开为实际 Unit 对象列表。
    返回 (units_list, error_msg)。无法匹配时返回 (None, error_msg)；
    非类别文本时返回 (None, None)。"""
    CATEGORY_PATTERNS = [
        (re.compile(r"\d*\s*个?\s*乡镇街道"), "乡镇街道"),
        (re.compile(r"\d*\s*个?\s*街道镇乡"), "乡镇街道"),
    ]
    for pattern, group_kw in CATEGORY_PATTERNS:
        if pattern.search(unit_name):
            matching = [g for g in plan_assessed_groups if group_kw in g.name]
            if matching:
                units = []
                for g in matching:
                    units.extend(g.units)
                return units, None
            return None, f"未找到包含「{group_kw}」的被考核分组"
    return None, None


def _split_unit_names(text):
    """按分隔符拆分单位名称列表，但跳过括号内的分隔符。
    如 '区农业农村委（区农技中心、区畜牧中心）' 不会被拆成两半。"""
    if not text:
        return []
    result = []
    current = []
    depth = 0
    for ch in text:
        if ch in "（([［":
            depth += 1
        elif ch in "）)]］":
            depth = max(0, depth - 1)
        if depth == 0 and ch in "、，,\n":
            name = "".join(current).strip()
            if name:
                result.append(name)
            current = []
        else:
            current.append(ch)
    name = "".join(current).strip()
    if name:
        result.append(name)
    return result


def _validate_import_rows(items, plan_id, plan_dims, plan_assessors, plan_assessed_units, plan_assessed_groups):
    """先校验所有行，返回 (valid_tasks, row_errors)。
    valid_tasks: [(row_idx, task_dict), ...] 待入库的任务字典
    row_errors: [(row_idx, error_msg), ...] 错误列表
    有任何一个错误都不入库，全量驳回。"""
    valid_tasks = []
    row_errors = []
    CATEGORY_KEYWORDS = ["个街道", "个部门", "个乡镇", "个乡镇街道", "各单位", "部分中央", "中小学校", "人民团体", "中央在黔"]

    for i, item in enumerate(items, 2):
        unit_name = item.get("unit", "")
        dim_name = item.get("dimension", "")
        assessor_name = item.get("assessor", "")
        key_work = item.get("key_work", "").strip()
        main_task = item.get("main_task", "").strip()
        scoring_note = item.get("scoring_note", "").strip()
        period = _normalize_period(item.get("period", ""))

        # 跳过无序号且全部关键字段为空的行
        seq = str(item.get("seq", ""))
        if seq and not seq.isdigit():
            if not any([unit_name, dim_name, assessor_name, key_work, main_task]):
                continue

        if not unit_name:
            row_errors.append((i, "被考核单位为空"))
            continue

        if not dim_name or not assessor_name or not key_work or not main_task:
            missing = []
            if not dim_name: missing.append("维度")
            if not assessor_name: missing.append("评价部门")
            if not key_work: missing.append("重点工作")
            if not main_task: missing.append("主要任务")
            row_errors.append((i, f"必填项为空：{'、'.join(missing)}"))
            continue

        dim, dim_err = _find_dim_in_set(dim_name, plan_dims)
        if dim_err:
            row_errors.append((i, dim_err))
            continue

        assessor, assessor_err = _find_unit_in_set(assessor_name, plan_assessors)
        if assessor_err:
            row_errors.append((i, f"评价部门{assessor_err}"))
            continue

        # 展开被考核单位
        target_units = []  # [(unit_obj, None)]

        # 1) 类别关键词展开（如 "30个乡镇街道" → 30个具体单位）
        if any(kw in unit_name for kw in CATEGORY_KEYWORDS):
            expanded, cat_err = _expand_category_units(unit_name, plan_assessed_groups)
            if cat_err:
                row_errors.append((i, cat_err))
                continue
            if expanded:
                target_units = [(u, None) for u in expanded]

        # 2) 非类别：按分隔符拆分单位名称列表
        if not target_units:
            unit_names = _split_unit_names(unit_name)
            if not unit_names:
                row_errors.append((i, "被考核单位为空"))
                continue
            for uname in unit_names:
                unit, unit_err = _find_unit_in_set(uname, plan_assessed_units)
                if unit_err:
                    row_errors.append((i, unit_err))
                    continue
                target_units.append((unit, None))

        if not target_units:
            row_errors.append((i, "无法解析被考核单位"))
            continue

        # 拆分主要任务 / 评分说明中的编号列表
        main_items, main_split = _split_numbered_items(main_task)
        score_items, score_split = _split_numbered_items(scoring_note)

        # 生成任务：编号拆分 × 单位展开
        if main_split:
            for idx, mt in enumerate(main_items):
                sn = score_items[idx] if score_split and idx < len(score_items) else scoring_note
                for unit, _ in target_units:
                    valid_tasks.append((i, {
                        "plan_id": plan_id,
                        "assessment_dimension_id": dim.id,
                        "unit_id": unit.id,
                        "assessor_unit_id": assessor.id,
                        "key_work": key_work,
                        "main_task": mt,
                        "scoring_note": sn,
                        "review_period": period,
                    }))
        else:
            for unit, _ in target_units:
                valid_tasks.append((i, {
                    "plan_id": plan_id,
                    "assessment_dimension_id": dim.id,
                    "unit_id": unit.id,
                    "assessor_unit_id": assessor.id,
                    "key_work": key_work,
                    "main_task": main_task,
                    "scoring_note": scoring_note,
                    "review_period": period,
                }))

    return valid_tasks, row_errors


@task_bp.route("/api/tasks/import", methods=["POST"])
@jwt_required()
def import_tasks():
    if "file" not in request.files:
        return jsonify({"msg": "请上传文件"}), 400

    file = request.files["file"]
    plan_id = request.form.get("plan_id", type=int)
    if not plan_id:
        return jsonify({"msg": "请指定考核方案"}), 400

    plan = Plan.query.get(plan_id)
    if not plan:
        return jsonify({"msg": "方案不存在"}), 404

    # 构建方案范围内的查找字典（仅允许导入方案预设的维度/主考单位/被考核单位）
    plan_dims = {}
    for ed in plan.evaluation_dimensions:
        for dim in ed.assessment_dimensions:
            plan_dims[dim.id] = dim
    plan_assessors = {u.id: u for u in plan.assessor_units}
    plan_assessed_units = {}
    for g in plan.assessed_groups:
        for u in g.units:
            plan_assessed_units[u.id] = u

    if not plan_dims:
        return jsonify({"msg": f"方案「{plan.name}」没有预设考核维度，请先在方案详情中配置"}), 400
    if not plan_assessors:
        return jsonify({"msg": f"方案「{plan.name}」没有设置主考单位，请先在方案详情中配置"}), 400
    if not plan_assessed_units:
        return jsonify({"msg": f"方案「{plan.name}」没有被考核分组，请先在方案详情中配置"}), 400

    filename = file.filename or "unknown.xlsx"
    file_bytes = file.read()

    # 通用工作簿读取（自动识别 .xls / .xlsx）
    wb_data = read_workbook(file_bytes, filename)
    if wb_data is None:
        return jsonify({"msg": "无法读取文件，请确认文件格式正确"}), 400
    if isinstance(wb_data, tuple):
        return jsonify({"msg": wb_data[1]}), 400

    # ========== 第一阶段：全量校验 ==========
    all_valid_tasks = []       # [(sheet_name, row_idx, task_dict), ...]
    all_row_errors = []        # [(sheet_name, row_idx, error_msg), ...]
    sheet_items_map = {}       # {sheet_name: [(row_idx, item_dict), ...]} 用于生成错误报告
    sheet_col_mapping = {}     # {sheet_name: col_mapping}
    sheet_header_idx = {}      # {sheet_name: header_row_idx}
    sheet_rows_raw = {}        # {sheet_name: raw_rows}

    for sname, rows in wb_data.items():
        if _should_skip_sheet(sname):
            continue
        if not rows or len(rows) < 2:
            continue

        header_row_idx = -1
        col_mapping = None

        for idx, row in enumerate(rows):
            h = [str(v).strip() if v else "" for v in row]
            if h == ["序号", "被考核单位", "维度", "评价部门", "重点工作", "主要任务", "评分说明", "晾晒周期"]:
                header_row_idx = idx
                col_mapping = {"seq": 0, "unit": 1, "dimension": 2, "assessor": 3, "key_work": 4, "main_task": 5, "scoring_note": 6, "period": 7}
                break
            if h == ["序号", "指标来源", "评价部门", "维度", "重点工作", "主要任务", "评分说明", "被考核对象", "晾晒周期", "备注"]:
                header_row_idx = idx
                col_mapping = {"seq": 0, "source": 1, "assessor": 2, "dimension": 3, "key_work": 4, "main_task": 5, "scoring_note": 6, "unit": 7, "period": 8, "remark": 9}
                break
            mapping = fuzzy_match_headers(h, HEADER_KEYWORDS)
            if mapping:
                header_row_idx = idx
                col_mapping = mapping
                break

        if header_row_idx < 0:
            all_row_errors.append((sname, 0, "未识别到表头行，请确认表头包含：评价部门、维度、重点工作、主要任务等"))
            continue

        sheet_header_idx[sname] = header_row_idx
        sheet_col_mapping[sname] = col_mapping
        sheet_rows_raw[sname] = rows

        items = []
        prev = {}
        for row in rows[header_row_idx + 1:]:
            if all(v is None for v in row):
                continue
            item = {}
            for field, col_idx in col_mapping.items():
                val = row[col_idx] if col_idx < len(row) else None
                item[field] = str(val).strip() if val is not None else ""
            if not item.get("dimension") and prev.get("dimension"):
                item["dimension"] = prev.get("dimension", "")
            items.append(item)
            prev = item

        sheet_items_map[sname] = [(header_row_idx + 2 + idx, item) for idx, item in enumerate(items)]

        valid_tasks, row_errors = _validate_import_rows(items, plan_id, plan_dims, plan_assessors, plan_assessed_units, plan.assessed_groups)
        all_valid_tasks.extend([(sname, idx, t) for idx, t in valid_tasks])
        all_row_errors.extend([(sname, idx, msg) for idx, msg in row_errors])

    # ========== 有错误：生成错误报告 Excel（摘要 + 各子表）并驳回全部导入 ==========
    if all_row_errors:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, Border, Side, PatternFill

        wb = Workbook()

        header_font = Font(name="黑体", bold=True, size=11)
        title_font = Font(name="黑体", bold=True, size=14)
        err_font = Font(name="仿宋", size=11, color="FF0000")
        normal_font = Font(name="仿宋", size=11)
        center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        left_align = Alignment(horizontal="left", vertical="center", wrap_text=True)
        thin_border = Border(
            left=Side(style="thin"), right=Side(style="thin"),
            top=Side(style="thin"), bottom=Side(style="thin")
        )
        header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
        err_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

        # 数据列名
        data_fields = ["序号", "被考核单位", "维度", "评价部门", "重点工作", "主要任务", "评分说明", "晾晒周期"]
        first_mapping = list(sheet_col_mapping.values())[0] if sheet_col_mapping else {}
        ordered_fields = [k for k in data_fields if k in first_mapping]
        for k in first_mapping:
            if k not in ordered_fields:
                ordered_fields.append(k)
        detail_headers = ["原行号"] + ordered_fields + ["错误说明"]

        # 按导入 sheet 分组错误
        errors_by_sheet = {}
        for sname, row_idx, msg in all_row_errors:
            if sname not in errors_by_sheet:
                errors_by_sheet[sname] = {}
            if row_idx not in errors_by_sheet[sname]:
                errors_by_sheet[sname][row_idx] = []
            errors_by_sheet[sname][row_idx].append(msg)

        # ==================== Sheet 1: 错误摘要 ====================
        ws_summary = wb.active
        ws_summary.title = "错误摘要"
        ws_summary.column_dimensions['A'].width = 22
        ws_summary.column_dimensions['B'].width = 65

        row = 1
        ws_summary.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
        title_cell = ws_summary.cell(row=row, column=1, value="考核任务导入 — 错误报告")
        title_cell.font = title_font
        title_cell.alignment = center_align
        row += 2

        summary_items = [
            ("导入方案", plan.name),
            ("导入文件", filename),
            ("导入工作表数", f"{len([s for s in wb_data if not _should_skip_sheet(s) and wb_data.get(s) and len(wb_data[s]) >= 2])} 个"),
            ("错误工作表数", f"{len(errors_by_sheet)} 个"),
            ("总错误条数", f"{len(all_row_errors)} 条"),
        ]
        for label, value in summary_items:
            ws_summary.cell(row=row, column=1, value=label).font = header_font
            ws_summary.cell(row=row, column=2, value=value).font = normal_font
            row += 1

        row += 1
        # 各工作表错误分布
        ws_summary.cell(row=row, column=1, value="各工作表错误分布").font = header_font
        row += 1
        dist_headers = ["工作表名称", "错误行数", "详细说明"]
        for ci, h in enumerate(dist_headers, 1):
            cell = ws_summary.cell(row=row, column=ci, value=h)
            cell.font = header_font
            cell.alignment = center_align
            cell.border = thin_border
            cell.fill = header_fill
        ws_summary.column_dimensions['C'].width = 60
        row += 1

        for sname, row_errs in errors_by_sheet.items():
            ws_summary.cell(row=row, column=1, value=sname).font = normal_font
            ws_summary.cell(row=row, column=2, value=f"{len(row_errs)} 行").font = normal_font
            # 汇总该 sheet 的所有错误类型
            error_types = {}
            for msgs in row_errs.values():
                for m in msgs:
                    key = m.split("：")[0] if "：" in m else m
                    error_types[key] = error_types.get(key, 0) + 1
            error_summary = "；".join(f"{k}({v}处)" for k, v in error_types.items())
            ws_summary.cell(row=row, column=3, value=error_summary).font = normal_font
            for ci in range(1, 4):
                ws_summary.cell(row=row, column=ci).border = thin_border
                ws_summary.cell(row=row, column=ci).alignment = center_align
            row += 1

        row += 1
        ws_summary.cell(row=row, column=1, value="处理方式").font = header_font
        ws_summary.cell(row=row, column=2, value="以上问题导致全部数据未导入。请按各子表标记修正后，重新导入全部数据。").font = Font(name="仿宋", size=11, color="FF0000")
        row += 1
        ws_summary.cell(row=row, column=1, value="子表说明").font = header_font
        ws_summary.cell(row=row, column=2, value="后续各子表按原工作表分列错误明细，含原始数据和具体错误原因，红色底色标记。").font = normal_font

        # ==================== 后续 Sheet：每个导入 sheet 一个错误明细子表 ====================
        for sname, row_errs in errors_by_sheet.items():
            safe_name = sname[:28]  # Excel sheet 名最多 31 字符
            ws_detail = wb.create_sheet(title=safe_name)

            # 表头
            for ci, h in enumerate(detail_headers, 1):
                cell = ws_detail.cell(row=1, column=ci, value=h)
                cell.font = header_font
                cell.alignment = center_align
                cell.border = thin_border
                cell.fill = header_fill
            ws_detail.column_dimensions['A'].width = 10
            for ci in range(2, len(detail_headers) + 1):
                ws_detail.column_dimensions[chr(64 + ci) if ci <= 26 else 'A'].width = 16
            ws_detail.column_dimensions[chr(64 + len(detail_headers)) if len(detail_headers) <= 26 else 'A'].width = 45

            detail_row = 2
            items = sheet_items_map.get(sname, [])
            for row_idx in sorted(row_errs.keys()):
                msgs = row_errs[row_idx]
                combined_msg = "；".join(msgs)

                original_item = None
                for idx, item in items:
                    if idx == row_idx:
                        original_item = item
                        break

                ws_detail.cell(row=detail_row, column=1, value=row_idx).font = normal_font
                ci = 2
                if original_item:
                    for field in ordered_fields:
                        cell = ws_detail.cell(row=detail_row, column=ci, value=original_item.get(field, ""))
                        cell.font = normal_font
                        cell.alignment = center_align
                        cell.border = thin_border
                        ci += 1
                else:
                    for _ in ordered_fields:
                        cell = ws_detail.cell(row=detail_row, column=ci, value="")
                        cell.alignment = center_align
                        cell.border = thin_border
                        ci += 1
                err_cell = ws_detail.cell(row=detail_row, column=ci, value=combined_msg)
                err_cell.font = err_font
                err_cell.alignment = left_align
                err_cell.fill = err_fill
                err_cell.border = thin_border

                for c in range(1, ci + 1):
                    ws_detail.cell(row=detail_row, column=c).fill = err_fill

                detail_row += 1

            ws_detail.freeze_panes = "B2"

        # 将错误摘要移到第一个位置
        wb.move_sheet("错误摘要", offset=-len(errors_by_sheet))

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        return send_file(output,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         as_attachment=True,
                         download_name=f"考核任务导入错误报告_{plan.name}.xlsx")

    # ========== 无错误：全部入库 ==========
    for sname, row_idx, task_dict in all_valid_tasks:
        db.session.add(Task(**task_dict))
    db.session.commit()

    return jsonify({
        "msg": f"全部校验通过，成功导入 {len(all_valid_tasks)} 个任务",
        "data": {"created": len(all_valid_tasks), "errors": 0},
    })


@task_bp.route("/api/tasks/template", methods=["GET"])
@jwt_required()
def download_template():
    fmt = request.args.get("fmt", "simple")
    if fmt == "detail":
        headers = ["序号", "指标来源", "评价部门", "维度", "重点工作", "主要任务", "评分说明", "被考核对象", "晾晒周期", "备注"]
        example = ["1", "市级考核", "区委办公室", "党建工作", "落实党的理论武装工作", "落实第一议题制度、理论学习中心组学习等", "未完成每项扣0.5分", "区司法局、区妇联", "月度", ""]
        fname = "考核任务导入模板_解构表.xlsx"
    else:
        headers = ["序号", "被考核单位", "维度", "评价部门", "重点工作", "主要任务", "评分说明", "晾晒周期"]
        example = ["1", "高新区管委会", "党建工作", "区委办公室", "落实党的理论武装工作", "落实第一议题制度、理论学习中心组学习等", "未完成每项扣0.5分", "月度"]
        fname = "考核任务导入模板.xlsx"
    output = export_xlsx(headers, [example])
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name=fname)


@task_bp.route("/api/tasks/export", methods=["GET"])
@jwt_required()
def export_tasks():
    user = _get_user(int(get_jwt_identity()))
    plan_id = request.args.get("plan_id", type=int)
    group_id = request.args.get("group_id", type=int)
    export_all = request.args.get("all", "")

    q = Task.query
    if plan_id:
        q = q.filter(Task.plan_id == plan_id)

    # 发布单位(系统管理员)看全部，不受 all 参数限制
    is_publisher = user and user.role and user.role.is_system
    if not export_all and user and not is_publisher:
        if user.current_identity == "assessed":
            q = q.filter(Task.unit_id == user.unit_id)
        elif user.current_identity == "assessor":
            q = q.filter(Task.assessor_unit_id == user.unit_id)

    if group_id:
        from models import AssessedGroup
        group = AssessedGroup.query.get(group_id)
        if group:
            unit_ids = [u.id for u in group.units]
            q = q.filter(Task.unit_id.in_(unit_ids))

    # 先按考核维度再按 ID 排序，同维度任务聚在一起
    tasks = q.join(AssessmentDimension, Task.assessment_dimension_id == AssessmentDimension.id)\
             .order_by(AssessmentDimension.name, Task.id).all()

    # 标题：{考核年度}年度考核任务书
    year = ""
    if plan_id:
        plan = Plan.query.get(plan_id)
        if plan:
            year = str(plan.year)
    title = f"{year}年度考核任务书" if year else "考核任务书"

    headers = ["序号", "被考核单位", "维度", "评价部门", "重点工作", "主要任务", "评分说明", "晾晒周期", "完成情况", "得分", "评语"]

    rows = []
    seq = 1
    for t in tasks:
        sub = t.submissions[-1].content if t.submissions else ""
        score_obj = t.scores[-1] if t.scores else None
        rows.append([
            seq,
            t.unit.name if t.unit else "",
            t.assessment_dimension.name if t.assessment_dimension else "",
            t.assessor_unit.name if t.assessor_unit else "",
            t.key_work,
            t.main_task,
            t.scoring_note or "",
            t.review_period,
            sub,
            score_obj.score if score_obj else "",
            score_obj.comment if score_obj else "",
        ])
        seq += 1

    output = export_gov_xlsx(title, headers, rows, merge_col=2)  # 维度列(第3列,0-based=2)合并
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="考核任务书.xlsx")


# ==================== 全量导出（按单位分包 ZIP） ====================

@task_bp.route("/api/tasks/export-all", methods=["GET"])
@jwt_required()
def export_all_tasks():
    user = _get_user(int(get_jwt_identity()))
    plan_id = request.args.get("plan_id", type=int)

    q = Task.query
    if plan_id:
        q = q.filter(Task.plan_id == plan_id)

    # 权限过滤（发布单位看全部）
    is_publisher = user and user.role and user.role.is_system
    if not is_publisher:
        if user and user.current_identity == "assessed":
            q = q.filter(Task.unit_id == user.unit_id)
        elif user and user.current_identity == "assessor":
            q = q.filter(Task.assessor_unit_id == user.unit_id)

    tasks = q.join(AssessmentDimension, Task.assessment_dimension_id == AssessmentDimension.id)\
             .order_by(Task.unit_id, AssessmentDimension.name, Task.id).all()

    # 按被考核单位分组
    unit_tasks = {}
    for t in tasks:
        unit_key = t.unit_id
        if unit_key not in unit_tasks:
            unit_tasks[unit_key] = {"name": t.unit.name if t.unit else "未知单位", "tasks": []}
        unit_tasks[unit_key]["tasks"].append(t)

    # 获取考核年度
    year = ""
    if plan_id:
        plan = Plan.query.get(plan_id)
        if plan:
            year = str(plan.year)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for unit_id, data in unit_tasks.items():
            unit_name = data["name"]
            unit_tasks_list = data["tasks"]

            # 标题：{年度}年度{单位名称}年度重点考核任务清单
            title = f"{year}年度{unit_name}年度重点考核任务清单" if year else f"{unit_name}任务书"
            headers = ["序号", "维度", "评价部门", "重点工作", "主要任务", "评分说明", "晾晒周期", "完成情况", "得分", "评语"]
            rows = []
            seq = 1
            for t in unit_tasks_list:
                sub = t.submissions[-1].content if t.submissions else ""
                score_obj = t.scores[-1] if t.scores else None
                rows.append([
                    seq,
                    t.assessment_dimension.name if t.assessment_dimension else "",
                    t.assessor_unit.name if t.assessor_unit else "",
                    t.key_work,
                    t.main_task,
                    t.scoring_note or "",
                    t.review_period,
                    sub,
                    score_obj.score if score_obj else "",
                    score_obj.comment if score_obj else "",
                ])
                seq += 1

            xlsx_buf = export_gov_xlsx(title, headers, rows, merge_col=1)  # 维度在第2列(0-based=1)
            safe_name = unit_name.replace("/", "_").replace("\\", "_")
            zf.writestr(f"{safe_name}任务书.xlsx", xlsx_buf.getvalue())

    zip_buf.seek(0)
    return send_file(zip_buf, mimetype="application/zip",
                     as_attachment=True, download_name="考核任务书_全量导出.zip")
