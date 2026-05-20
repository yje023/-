import io, zipfile
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
    assessor_unit_id = request.args.get("assessor_unit_id", type=int)
    unit_id = request.args.get("unit_id", type=int)
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    page_size = min(page_size, 200)

    q = Task.query
    if plan_id:
        q = q.filter(Task.plan_id == plan_id)
    if status:
        q = q.filter(Task.status == status)
    if assessor_unit_id:
        q = q.filter(Task.assessor_unit_id == assessor_unit_id)
    if unit_id:
        q = q.filter(Task.unit_id == unit_id)
    if search:
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


def _task_to_dict(t):
    return {
        "id": t.id,
        "plan_id": t.plan_id,
        "assessment_dimension_id": t.assessment_dimension_id,
        "dimension_name": t.assessment_dimension.name if t.assessment_dimension else "",
        "unit_id": t.unit_id,
        "unit_name": t.unit.name if t.unit else "",
        "assessor_unit_id": t.assessor_unit_id,
        "assessor_unit_name": t.assessor_unit.name if t.assessor_unit else "",
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

def _find_unit(name):
    """查找单位：精确匹配 → 模糊匹配降级（唯一匹配才返回）"""
    name = _normalize_name(name)
    unit = Unit.query.filter_by(name=name).first()
    if unit:
        return unit, None
    # 精确匹配规范化后的名称
    candidates = Unit.query.filter(Unit.name == name).all()
    if len(candidates) == 1:
        return candidates[0], None
    # 模糊匹配降级
    candidates = Unit.query.filter(Unit.name.contains(name)).all()
    if len(candidates) == 1:
        return candidates[0], None
    elif len(candidates) > 1:
        return None, f"单位名称「{name}」匹配到多个单位：{', '.join(u.name for u in candidates[:5])}"
    candidates = Unit.query.filter(Unit.name.contains(name.replace('区', ''))).all()
    if len(candidates) == 1:
        return candidates[0], None
    return None, f"单位「{name}」不存在"


def _find_dim(name):
    """查找考核维度：精确匹配 → 模糊匹配降级"""
    name = _normalize_name(name)
    dim = AssessmentDimension.query.filter_by(name=name).first()
    if dim:
        return dim, None
    # 精确匹配规范化后的名称
    candidates = AssessmentDimension.query.filter(AssessmentDimension.name == name).all()
    if len(candidates) == 1:
        return candidates[0], None
    candidates = AssessmentDimension.query.filter(AssessmentDimension.name.contains(name)).all()
    if len(candidates) == 1:
        return candidates[0], None
    return None, f"考核维度「{name}」不存在"


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


def _import_unified_rows(items, plan_id):
    """统一导入：items = [{field: value}, ...]，返回 (created, errors)。
    使用模糊匹配查找单位和维度，支持多被考核单位（顿号分隔）。"""
    created = 0
    # 被考核单位类别描述关键词（非具体单位名，应跳过）
    CATEGORY_KEYWORDS = ["个街道", "个部门", "个乡镇", "个乡镇街道", "各单位", "部分中央", "中小学校", "人民团体", "中央在黔"]

    errors = []
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
        skip = False
        if seq and not seq.isdigit():
            if not any([unit_name, dim_name, assessor_name, key_work, main_task]):
                continue
            skip = True

        if not unit_name:
            errors.append(f"第{i}行：被考核单位为空")
            continue
        # 跳过类别描述（如"30个街道镇乡"）
        if any(kw in unit_name for kw in CATEGORY_KEYWORDS):
            continue
        if not dim_name or not assessor_name or not key_work or not main_task:
            errors.append(f"第{i}行：有必填项为空（维度/评价部门/重点工作/主要任务）")
            continue

        dim, dim_err = _find_dim(dim_name)
        if dim_err:
            errors.append(f"第{i}行：{dim_err}")
            continue

        assessor, assessor_err = _find_unit(assessor_name)
        if assessor_err:
            errors.append(f"第{i}行：评价部门{assessor_err}")
            continue

        # 被考核单位可能为多个（顿号或中文逗号分隔）
        unit_name_list = [u.strip() for u in unit_name.replace("，", "、").split("、") if u.strip()]
        if not unit_name_list:
            errors.append(f"第{i}行：被考核单位为空")
            continue

        for uname in unit_name_list:
            unit, unit_err = _find_unit(uname)
            if unit_err:
                errors.append(f"第{i}行：{unit_err}")
                continue

            db.session.add(Task(
                plan_id=plan_id, assessment_dimension_id=dim.id,
                unit_id=unit.id, assessor_unit_id=assessor.id,
                key_work=key_work, main_task=main_task,
                scoring_note=scoring_note,
                review_period=period,
            ))
            created += 1
    return created, errors


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

    filename = file.filename or "unknown.xlsx"
    file_bytes = file.read()

    # 通用工作簿读取（自动识别 .xls / .xlsx）
    wb_data = read_workbook(file_bytes, filename)
    if wb_data is None:
        return jsonify({"msg": "无法读取文件，请确认文件格式正确"}), 400
    if isinstance(wb_data, tuple):
        return jsonify({"msg": wb_data[1]}), 400

    total_created = 0
    all_errors = []

    for sname, rows in wb_data.items():
        if _should_skip_sheet(sname):
            continue
        if not rows or len(rows) < 2:
            continue

        # 扫描找到表头行：先尝试精确匹配，再尝试模糊匹配
        header_row_idx = -1
        col_mapping = None

        for idx, row in enumerate(rows):
            h = [str(v).strip() if v else "" for v in row]
            # 精确匹配（保留向后兼容）
            if h == ["序号", "被考核单位", "维度", "评价部门", "重点工作", "主要任务", "评分说明", "晾晒周期"]:
                header_row_idx = idx
                col_mapping = {"seq": 0, "unit": 1, "dimension": 2, "assessor": 3, "key_work": 4, "main_task": 5, "scoring_note": 6, "period": 7}
                break
            if h == ["序号", "指标来源", "评价部门", "维度", "重点工作", "主要任务", "评分说明", "被考核对象", "晾晒周期", "备注"]:
                header_row_idx = idx
                col_mapping = {"seq": 0, "source": 1, "assessor": 2, "dimension": 3, "key_work": 4, "main_task": 5, "scoring_note": 6, "unit": 7, "period": 8, "remark": 9}
                break
            # 模糊匹配
            mapping = fuzzy_match_headers(h, HEADER_KEYWORDS)
            if mapping:
                header_row_idx = idx
                col_mapping = mapping
                break

        if header_row_idx < 0:
            all_errors.append(f"[{sname}] 未识别到表头行，请确认表头包含：评价部门、维度、重点工作、主要任务等")
            continue

        # 提取数据行并做标准化
        items = []
        prev = {}
        for row in rows[header_row_idx + 1:]:
            if all(v is None for v in row):
                continue
            item = {}
            for field, col_idx in col_mapping.items():
                val = row[col_idx] if col_idx < len(row) else None
                item[field] = str(val).strip() if val is not None else ""
            # 向前填充维度列
            if not item.get("dimension") and prev.get("dimension"):
                item["dimension"] = prev.get("dimension", "")
            items.append(item)
            prev = item

        c, errs = _import_unified_rows(items, plan_id)
        total_created += c
        all_errors.extend([f"[{sname}] {e}" for e in errs])

    db.session.commit()

    result = {
        "msg": f"成功导入 {total_created} 个任务",
        "data": {"created": total_created, "errors": len(all_errors)},
    }
    if all_errors:
        result["errors"] = all_errors[:100]
    return jsonify(result)


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
