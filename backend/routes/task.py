import io, re, zipfile
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.orm import joinedload
from models import db, Task, TaskSubmission, TaskScore, Plan, AssessmentDimension, Unit, User, QualityIssue, ConfirmedPattern, ProxyMetricPair, ProcessLog
from utils.xlsx_handler import export_xlsx, export_gov_xlsx, read_workbook, fuzzy_match_headers, HEADER_KEYWORDS
from services.task_query import build_task_query

task_bp = Blueprint("task", __name__)


def _get_user(user_id):
    return User.query.get(user_id)


def _add_process_log(task_id, plan_id, action, from_status, to_status, operator_id, comment=None):
    """记录操作日志"""
    log = ProcessLog(
        task_id=task_id,
        plan_id=plan_id,
        action=action,
        from_status=from_status,
        to_status=to_status,
        operator_id=operator_id,
        comment=comment,
    )
    db.session.add(log)


@task_bp.route("/api/tasks", methods=["GET"])
@jwt_required()
def list_tasks():
    user = _get_user(int(get_jwt_identity()))
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    page_size = min(page_size, 200)

    q = build_task_query(
        plan_id=request.args.get("plan_id", type=int),
        status=request.args.get("status", "").strip(),
        search=request.args.get("search", "").strip(),
        search_type=request.args.get("search_type", "all").strip(),
        assessor_unit_id=request.args.get("assessor_unit_id", "").strip(),
        unit_id=request.args.get("unit_id", "").strip(),
        dimension_ids=request.args.get("dimension_ids", "").strip(),
        key_works=request.args.get("key_works", "").strip(),
        period=request.args.get("period", "").strip(),
        user=user,
    )

    total = q.count()
    tasks = q.options(
        joinedload(Task.assessment_dimension),
        joinedload(Task.unit),
        joinedload(Task.assessor_unit),
        joinedload(Task.submissions),
        joinedload(Task.scores),
    ).order_by(Task.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    data = [_task_to_dict(t) for t in tasks]
    return jsonify({"data": {"items": data, "total": total, "page": page, "page_size": page_size}})


@task_bp.route("/api/tasks/filter-options", methods=["GET"])
@jwt_required()
def filter_options():
    """返回当前方案下可筛选的维度、重点工作、评价部门、被考核单位，支持级联禁用"""
    import json as _json
    user = _get_user(int(get_jwt_identity()))
    plan_id = request.args.get("plan_id", type=int)
    current_filters_str = request.args.get("current_filters", "{}")

    try:
        current_filters = _json.loads(current_filters_str)
    except (_json.JSONDecodeError, TypeError):
        current_filters = {}

    # 基础查询
    base_q = Task.query
    if plan_id:
        base_q = base_q.filter(Task.plan_id == plan_id)

    is_publisher = user and user.role and user.role.is_system
    if not is_publisher:
        if user and user.current_identity == "assessed":
            base_q = base_q.filter(Task.unit_id == user.unit_id)
        elif user and user.current_identity == "assessor":
            base_q = base_q.filter(Task.assessor_unit_id == user.unit_id)

    # 获取基础 task ids（用于后续查询）
    base_task_ids = [t[0] for t in base_q.with_entities(Task.id).all()]
    if not base_task_ids:
        return jsonify({"data": {"dimensions": [], "key_works": [], "assessor_units": [], "assessed_units": [], "review_periods": []}})

    def _safe_int_list(values):
        """安全地将字符串列表转为整数列表"""
        result = []
        for v in values:
            try: result.append(int(v))
            except (ValueError, TypeError): pass
        return result

    def _filtered_task_ids(exclude_dim):
        """返回排除某个维度筛选后的 task id 集合"""
        ids = set(base_task_ids)
        filters = {k: v for k, v in current_filters.items() if k != exclude_dim and v}
        if not filters:
            return ids

        q = base_q
        if filters.get("dimension"):
            dim_ids = _safe_int_list(filters["dimension"])
            if dim_ids: q = q.filter(Task.assessment_dimension_id.in_(dim_ids))
        if filters.get("key_work"):
            q = q.filter(Task.key_work.in_(filters["key_work"]))
        if filters.get("assessor"):
            a_ids = _safe_int_list(filters["assessor"])
            if a_ids: q = q.filter(Task.assessor_unit_id.in_(a_ids))
        if filters.get("unit"):
            u_ids = _safe_int_list(filters["unit"])
            if u_ids: q = q.filter(Task.unit_id.in_(u_ids))
        if filters.get("period"):
            q = q.filter(Task.review_period.in_(filters["period"]))
        return set(t[0] for t in q.with_entities(Task.id).all())

    def _batch_counts(tid_set, column):
        """批量计数：对 tid_set 按指定列 GROUP BY，一次查询返回 {value: count}"""
        if not tid_set:
            return {}
        rows = (
            db.session.query(column, db.func.count(Task.id))
            .filter(Task.id.in_(list(tid_set)))
            .group_by(column).all()
        )
        return {r[0]: r[1] for r in rows if r[0] is not None}

    PERIOD_LABELS = {"月度": "月度", "季度": "季度", "半年度": "半年度", "年度": "年度"}

    # 所有维度查询：ALL = 从全部任务取去重值（base_task_ids），ACTIVE = 从筛选后任务计数（filtered_task_ids）
    # 这样零匹配选项仍会出现在列表中（前端可显示为红色），不会消失

    # 考核维度：从全部任务取去重
    all_dim_tids = base_task_ids
    dim_tids = _filtered_task_ids("dimension")
    dims = (
        db.session.query(AssessmentDimension.id, AssessmentDimension.name)
        .join(Task, Task.assessment_dimension_id == AssessmentDimension.id)
        .filter(Task.id.in_(list(all_dim_tids)) if all_dim_tids else False)
        .distinct().order_by(AssessmentDimension.name).all()
    )
    dim_counts = _batch_counts(dim_tids, Task.assessment_dimension_id)
    # active: 在当前筛选下 count > 0
    dimensions = [{"id": d[0], "name": d[1], "active": dim_counts.get(d[0], 0) > 0, "count": dim_counts.get(d[0], 0)} for d in dims]

    # 重点工作：从全部任务取去重
    kw_tids = _filtered_task_ids("key_work")
    all_kws = (
        db.session.query(Task.key_work)
        .filter(Task.id.in_(list(base_task_ids)), Task.key_work.isnot(None), Task.key_work != "")
        .distinct().order_by(Task.key_work).all()
    )
    kw_counts = _batch_counts(kw_tids, Task.key_work)
    key_works = [{"id": k[0], "name": k[0], "active": kw_counts.get(k[0], 0) > 0, "count": kw_counts.get(k[0], 0)} for k in all_kws if k[0]]

    # 评价部门：从全部任务取去重
    assessor_tids = _filtered_task_ids("assessor")
    all_assessors = (
        db.session.query(Unit.id, Unit.name)
        .join(Task, Task.assessor_unit_id == Unit.id)
        .filter(Task.id.in_(list(base_task_ids)))
        .distinct().order_by(Unit.name).all()
    )
    assessor_counts = _batch_counts(assessor_tids, Task.assessor_unit_id)
    assessor_units = [{"id": a[0], "name": a[1], "active": assessor_counts.get(a[0], 0) > 0, "count": assessor_counts.get(a[0], 0)} for a in all_assessors]

    # 被考核单位：从全部任务取去重
    unit_tids = _filtered_task_ids("unit")
    all_units = (
        db.session.query(Unit.id, Unit.name)
        .join(Task, Task.unit_id == Unit.id)
        .filter(Task.id.in_(list(base_task_ids)))
        .distinct().order_by(Unit.name).all()
    )
    unit_counts = _batch_counts(unit_tids, Task.unit_id)
    assessed_units = [{"id": u[0], "name": u[1], "active": unit_counts.get(u[0], 0) > 0, "count": unit_counts.get(u[0], 0)} for u in all_units]

    # 晾晒周期：固定列表
    period_tids = _filtered_task_ids("period")
    period_counts = _batch_counts(period_tids, Task.review_period)
    review_periods = [{"id": k, "name": v, "active": period_counts.get(k, 0) > 0, "count": period_counts.get(k, 0)} for k, v in PERIOD_LABELS.items()]

    return jsonify({"data": {
        "dimensions": dimensions,
        "key_works": key_works,
        "assessor_units": assessor_units,
        "assessed_units": assessed_units,
        "review_periods": review_periods,
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
        "rejection_reason": t.rejection_reason or "",
        "task_source": t.task_source or "direct",
        "distributed_at": str(t.distributed_at) if t.distributed_at else None,
        "confirmed_at": str(t.confirmed_at) if t.confirmed_at else None,
        "completed_at": str(t.completed_at) if t.completed_at else None,
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

    initial_status = data.get("status", "pending")
    if initial_status not in ("pending", "draft"):
        initial_status = "pending"

    user = _get_user(int(get_jwt_identity()))
    task = Task(
        plan_id=data["plan_id"],
        assessment_dimension_id=data["assessment_dimension_id"],
        unit_id=data["unit_id"],
        assessor_unit_id=data["assessor_unit_id"],
        key_work=data["key_work"].strip(),
        main_task=data["main_task"].strip(),
        scoring_note=data.get("scoring_note", "").strip(),
        review_period=data["review_period"],
        status=initial_status,
        task_source=data.get("task_source", "direct"),
    )
    db.session.add(task)
    db.session.flush()  # 获取 task.id
    if user:
        _add_process_log(task.id, task.plan_id, "create", None, initial_status, user.id)
    db.session.commit()
    return jsonify({"msg": "创建成功", "data": {"id": task.id}})


@task_bp.route("/api/tasks/<int:task_id>", methods=["PUT"])
@jwt_required()
def update_task(task_id):
    task = Task.query.get(task_id)
    if not task:
        return jsonify({"msg": "任务不存在"}), 404

    if task.status in ("confirmed", "completed"):
        return jsonify({"msg": "已确认/已完成的任务不可编辑，请先通过管理员解除确认"}), 403

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
    if task.status in ("confirmed", "completed"):
        return jsonify({"msg": "已确认/已完成的任务不可删除"}), 403
    db.session.delete(task)
    db.session.commit()
    return jsonify({"msg": "删除成功"})


@task_bp.route("/api/tasks/<int:task_id>", methods=["GET"])
@jwt_required()
def get_task(task_id):
    """获取单条任务详情（含预加载关联数据）"""
    task = Task.query.options(
        joinedload(Task.assessment_dimension),
        joinedload(Task.unit),
        joinedload(Task.assessor_unit),
        joinedload(Task.submissions),
        joinedload(Task.scores),
    ).get(task_id)
    if not task:
        return jsonify({"msg": "任务不存在"}), 404
    return jsonify({"data": _task_to_dict(task)})


@task_bp.route("/api/tasks/batch-all", methods=["DELETE"])
@jwt_required()
def batch_delete_all_tasks():
    """删除指定方案的全部考核任务（含关联质量检查、确认模式、代理指标）"""
    plan_id = request.args.get("plan_id", type=int)
    q = Task.query
    if plan_id:
        q = q.filter_by(plan_id=plan_id)
    count = q.count()
    if count == 0:
        return jsonify({"msg": "没有可删除的任务"}), 200

    # 同步清理关联数据
    task_ids = [t.id for t in q.all()]

    # 清理代理指标对
    if task_ids:
        ProxyMetricPair.query.filter(
            ProxyMetricPair.task_id_a.in_(task_ids) | ProxyMetricPair.task_id_b.in_(task_ids)
        ).delete(synchronize_session=False)

    # 清理确认模式（按方案）
    if plan_id:
        ConfirmedPattern.query.filter_by(plan_id=plan_id).delete(synchronize_session=False)

    # 清理操作日志
    ProcessLog.query.filter(ProcessLog.task_id.in_(task_ids)).delete(synchronize_session=False)

    # 清理质量检查（cascade 会自动处理，此处作为兜底）
    QualityIssue.query.filter(QualityIssue.task_id.in_(task_ids)).delete(synchronize_session=False)

    # 删除任务（cascade 同时删除 submissions、scores、quality_issues）
    q.delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"msg": f"成功删除 {count} 个任务", "data": {"deleted": count}})


@task_bp.route("/api/tasks/batch-delete", methods=["POST"])
@jwt_required()
def batch_delete_tasks():
    """批量删除指定ID的任务"""
    data = request.get_json()
    ids = data.get("ids", [])
    if not ids:
        return jsonify({"msg": "请选择要删除的任务"}), 400
    ProcessLog.query.filter(ProcessLog.task_id.in_(ids)).delete(synchronize_session=False)
    Task.query.filter(Task.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"msg": f"已删除 {len(ids)} 个任务"})


@task_bp.route("/api/tasks/<int:task_id>/review", methods=["PUT"])
@jwt_required()
def review_task(task_id):
    task = Task.query.get(task_id)
    if not task:
        return jsonify({"msg": "任务不存在"}), 404
    if task.status not in ("submitted",):
        return jsonify({"msg": f"当前状态「{task.status}」不可审核，仅已提交状态可审核"}), 403

    user = _get_user(int(get_jwt_identity()))
    data = request.get_json()
    old_status = task.status
    new_status = data.get("status", "reviewed")
    if new_status not in ("reviewed", "rejected"):
        return jsonify({"msg": "无效的目标状态"}), 400
    task.status = new_status
    if new_status == "rejected":
        task.rejection_reason = data.get("rejection_reason", "")
    _add_process_log(task.id, task.plan_id, "reject" if new_status == "rejected" else "review",
                     old_status, new_status, user.id,
                     comment=data.get("rejection_reason", "") if new_status == "rejected" else None)
    db.session.commit()
    return jsonify({"msg": "驳回成功" if new_status == "rejected" else "审核完成"})


# ==================== v1.5 状态机操作 ====================

@task_bp.route("/api/tasks/<int:task_id>/reject", methods=["PUT"])
@jwt_required()
def reject_task(task_id):
    """驳回任务: submitted → rejected"""
    task = Task.query.get(task_id)
    if not task:
        return jsonify({"msg": "任务不存在"}), 404
    if task.status not in ("submitted",):
        return jsonify({"msg": f"当前状态「{task.status}」不可驳回，仅已提交状态可驳回"}), 403

    user = _get_user(int(get_jwt_identity()))
    # 权限：系统管理员 或 主考单位
    is_admin = user.role and user.role.is_system
    is_assessor = user.current_identity == "assessor" and user.unit_id == task.assessor_unit_id
    if not (is_admin or is_assessor):
        return jsonify({"msg": "仅主考单位或管理员可驳回任务"}), 403

    data = request.get_json()
    reason = data.get("reason", "").strip()
    if not reason:
        return jsonify({"msg": "驳回原因不能为空"}), 400

    old_status = task.status
    task.status = "rejected"
    task.rejection_reason = reason
    _add_process_log(task.id, task.plan_id, "reject", old_status, "rejected", user.id, comment=reason)
    db.session.commit()
    return jsonify({"msg": "驳回成功"})


@task_bp.route("/api/tasks/<int:task_id>/resubmit", methods=["PUT"])
@jwt_required()
def resubmit_task(task_id):
    """重提任务: rejected → pending（被考核单位修改后重提）"""
    task = Task.query.get(task_id)
    if not task:
        return jsonify({"msg": "任务不存在"}), 404
    if task.status not in ("rejected",):
        return jsonify({"msg": f"当前状态「{task.status}」不可重提，仅已驳回状态可重提"}), 403

    user = _get_user(int(get_jwt_identity()))
    if user.unit_id != task.unit_id:
        return jsonify({"msg": "仅被考核单位可重提"}), 403

    old_status = task.status
    task.status = "pending"
    task.rejection_reason = None  # 清除旧驳回原因
    _add_process_log(task.id, task.plan_id, "resubmit", old_status, "pending", user.id)
    db.session.commit()
    return jsonify({"msg": "已重提，可重新编辑提交"})


@task_bp.route("/api/tasks/<int:task_id>/confirm", methods=["PUT"])
@jwt_required()
def confirm_task(task_id):
    """确认任务纳入任务书: reviewed → confirmed（快照数据）"""
    task = Task.query.get(task_id)
    if not task:
        return jsonify({"msg": "任务不存在"}), 404
    if task.status not in ("reviewed",):
        return jsonify({"msg": f"当前状态「{task.status}」不可确认，仅已审核状态可确认"}), 403

    user = _get_user(int(get_jwt_identity()))
    if not (user.role and user.role.is_system):
        return jsonify({"msg": "仅管理员可确认任务书"}), 403

    import json as _json
    # 生成快照数据
    snapshot = {
        "key_work": task.key_work,
        "main_task": task.main_task,
        "scoring_note": task.scoring_note or "",
        "review_period": task.review_period,
        "unit_name": task.unit.name if task.unit else "",
        "assessor_unit_name": task.assessor_unit.name if task.assessor_unit else "",
        "dimension_name": task.assessment_dimension.name if task.assessment_dimension else "",
        "submissions": [{"content": s.content, "submitted_at": str(s.submitted_at)} for s in task.submissions],
        "scores": [{"score": s.score, "comment": s.comment or "", "scored_at": str(s.scored_at)} for s in task.scores],
    }

    old_status = task.status
    task.status = "confirmed"
    task.confirmed_at = datetime.utcnow()
    task.snapshot_data = _json.dumps(snapshot, ensure_ascii=False)
    _add_process_log(task.id, task.plan_id, "confirm", old_status, "confirmed", user.id)
    db.session.commit()
    return jsonify({"msg": "已确认纳入任务书"})


@task_bp.route("/api/tasks/batch-distribute", methods=["POST"])
@jwt_required()
def batch_distribute_tasks():
    """批量分发任务：draft → pending，任务由不可见变为对考核单位可见"""
    data = request.get_json()
    task_ids = data.get("task_ids", [])
    if not task_ids:
        return jsonify({"msg": "请选择要分发的任务"}), 400

    user = _get_user(int(get_jwt_identity()))
    if not (user.role and user.role.is_system):
        return jsonify({"msg": "仅管理员可分发任务"}), 403

    tasks = Task.query.filter(Task.id.in_(task_ids), Task.status == "draft").all()
    if not tasks:
        return jsonify({"msg": "没有可分发的草稿任务（仅草稿状态可分发）"}), 400

    plan_id_set = set(t.plan_id for t in tasks)
    if len(plan_id_set) > 1:
        return jsonify({"msg": "只能批量分发同一方案下的草稿任务"}), 400

    now = datetime.utcnow()
    count = 0
    for task in tasks:
        old_status = task.status
        task.status = "pending"
        task.distributed_at = now
        task.distributed_by = user.id
        _add_process_log(task.id, task.plan_id, "distribute", old_status, "pending", user.id)
        count += 1

    db.session.commit()
    return jsonify({"msg": f"成功分发 {count} 个任务，被考核单位现在可见", "data": {"distributed": count}})


@task_bp.route("/api/tasks/<int:task_id>/complete", methods=["PUT"])
@jwt_required()
def complete_task(task_id):
    """完成任务: confirmed → completed"""
    task = Task.query.get(task_id)
    if not task:
        return jsonify({"msg": "任务不存在"}), 404
    if task.status not in ("confirmed",):
        return jsonify({"msg": f"当前状态「{task.status}」不可完成，仅已确认状态可标记完成"}), 403

    user = _get_user(int(get_jwt_identity()))
    if not (user.role and user.role.is_system):
        return jsonify({"msg": "仅管理员可标记完成"}), 403

    old_status = task.status
    task.status = "completed"
    task.completed_at = datetime.utcnow()
    _add_process_log(task.id, task.plan_id, "complete", old_status, "completed", user.id)
    db.session.commit()
    return jsonify({"msg": "已标记完成"})


@task_bp.route("/api/tasks/<int:task_id>/history", methods=["GET"])
@jwt_required()
def get_task_history(task_id):
    """获取任务操作历史"""
    task = Task.query.get(task_id)
    if not task:
        return jsonify({"msg": "任务不存在"}), 404

    logs = ProcessLog.query.filter_by(task_id=task_id).order_by(ProcessLog.created_at.desc()).all()
    history = []
    for log in logs:
        operator_name = log.operator.username if log.operator else "未知"
        history.append({
            "id": log.id,
            "action": log.action,
            "from_status": log.from_status,
            "to_status": log.to_status,
            "comment": log.comment or "",
            "operator_name": operator_name,
            "created_at": str(log.created_at),
        })

    return jsonify({"data": {"task_id": task_id, "history": history}})


# ==================== 填报打分 ====================

@task_bp.route("/api/tasks/<int:task_id>/submit", methods=["POST"])
@jwt_required()
def submit_task(task_id):
    task = Task.query.get(task_id)
    if not task:
        return jsonify({"msg": "任务不存在"}), 404

    if task.status not in ("pending",):
        return jsonify({"msg": f"当前状态「{task.status}」不可提交，仅待办状态可提交"}), 403

    user = _get_user(int(get_jwt_identity()))
    if user.unit_id != task.unit_id:
        return jsonify({"msg": "仅被考核单位可填报"}), 403

    data = request.get_json()
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"msg": "填报内容不能为空"}), 400

    submission = TaskSubmission(task_id=task.id, content=content)
    db.session.add(submission)
    old_status = task.status
    task.status = "submitted"
    _add_process_log(task.id, task.plan_id, "submit", old_status, "submitted", user.id)
    db.session.commit()
    return jsonify({"msg": "提交成功"})


@task_bp.route("/api/tasks/<int:task_id>/score", methods=["POST"])
@jwt_required()
def score_task(task_id):
    task = Task.query.get(task_id)
    if not task:
        return jsonify({"msg": "任务不存在"}), 404

    if task.status not in ("submitted",):
        return jsonify({"msg": f"当前状态「{task.status}」不可评分，仅已提交状态可评分"}), 403

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

    old_status = task.status
    task.status = "reviewed"
    _add_process_log(task.id, task.plan_id, "review", old_status, "reviewed", user.id,
                     comment=f"评分: {score_val}" + (f", 评语: {data.get('comment', '')}" if data.get('comment') else ""))
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


def _levenshtein_distance(s1, s2):
    """纯 Python 编辑距离计算（Levenshtein Distance）"""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(
                prev[j + 1] + 1,      # insertion
                curr[j] + 1,          # deletion
                prev[j] + (c1 != c2)  # substitution
            ))
        prev = curr
    return prev[-1]


def _fuzzy_match_name(name, candidates, get_name_fn, max_dist_ratio=0.5, max_dist_abs=3):
    """三级回退匹配：精确匹配 → 子串包含 → 编辑距离
    candidates: 可迭代的候选项列表
    get_name_fn: 从候选项提取名称字符串的函数
    返回: (matched_obj, confidence) 或 (None, None)
    """
    if not name or not candidates:
        return None, None
    name = _normalize_name(name)
    candidate_list = list(candidates)

    # 1) 精确匹配
    for obj in candidate_list:
        if _normalize_name(get_name_fn(obj)) == name:
            return obj, "exact"

    # 2) 子串包含 — 输入名是候选名的子串（简称匹配，如"区委办" in "区委办公室"）
    substring_matches = [obj for obj in candidate_list if name in _normalize_name(get_name_fn(obj))]
    if len(substring_matches) == 1:
        return substring_matches[0], "substring"

    # 2b) 反向子串 — 候选名是输入名的子串（如输入"区健康管理中心区卫生健康发展中心"，候选"区健康管理中心"）
    reverse_matches = [obj for obj in candidate_list if _normalize_name(get_name_fn(obj)) in name and _normalize_name(get_name_fn(obj))]
    if len(reverse_matches) == 1:
        return reverse_matches[0], "substring"
    elif len(reverse_matches) > 1:
        # 多个候选都包含在输入中 → 取最长的（最精确）
        reverse_matches.sort(key=lambda obj: len(_normalize_name(get_name_fn(obj))), reverse=True)
        longest = reverse_matches[0]
        second = reverse_matches[1] if len(reverse_matches) > 1 else None
        if second and len(_normalize_name(get_name_fn(longest))) == len(_normalize_name(get_name_fn(second))):
            pass  # 平局，不匹配，继续走编辑距离
        else:
            return longest, "substring"

    # 3) 编辑距离（取最佳唯一匹配）
    best_obj, best_dist = None, None
    for obj in candidate_list:
        dist = _levenshtein_distance(name, _normalize_name(get_name_fn(obj)))
        max_allowed = min(int(len(name) * max_dist_ratio), max_dist_abs)
        if dist <= max_allowed:
            if best_dist is None or dist < best_dist:
                best_obj, best_dist = obj, dist
            elif dist == best_dist:
                best_obj = None  # 平局，不匹配
    if best_obj is not None:
        return best_obj, "edit_distance"

    return None, None


def _find_unit_in_set_fuzzy(name, unit_dict):
    """带模糊匹配的单位查找：精确→子串→编辑距离，返回 (unit, error, suggestion, suggestion_id)"""
    name = _normalize_name(name)
    # 先用原有逻辑
    unit, err = _find_unit_in_set(name, unit_dict)
    if unit:
        return unit, None, None, None
    # 再用编辑距离模糊匹配
    candidates = list(unit_dict.values())
    match, confidence = _fuzzy_match_name(name, candidates, lambda u: u.name)
    if match:
        return match, None, match.name, match.id
    # 尝试分隔符拆分后逐个匹配
    parts = _split_unit_names(name)
    if len(parts) > 1:
        matched_parts = []
        for part in parts:
            m, _ = _fuzzy_match_name(_normalize_name(part), candidates, lambda u: u.name)
            if m:
                matched_parts.append(m)
        if len(matched_parts) == len(parts):
            # 所有部分都匹配到了（但不能合成为一个 unit，这里只对单个 unit 做建议）
            pass
    return None, err, None, None


def _find_dim_in_set_fuzzy(name, dim_dict):
    """带模糊匹配的维度查找：精确→子串→编辑距离，返回 (dim, error, suggestion, suggestion_id)"""
    name = _normalize_name(name)
    dim, err = _find_dim_in_set(name, dim_dict)
    if dim:
        return dim, None, None, None
    candidates = list(dim_dict.values())
    match, confidence = _fuzzy_match_name(name, candidates, lambda d: d.name)
    if match:
        return match, None, match.name, match.id
    return None, err, None, None


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


def _exact_match_name(name, candidates_dict):
    """纯精确匹配：只做 normalize 后逐对比较，不降级到模糊匹配。
    candidates_dict: {id: obj} 字典
    返回: (obj, None) 或 (None, error_msg)"""
    if not name:
        return None, "名称为空"
    nn = _normalize_name(name)
    for obj in candidates_dict.values():
        if _normalize_name(obj.name) == nn:
            return obj, None
    return None, f"「{name}」不在预设中，请检查名称是否完全正确"


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


def _validate_import_rows_fuzzy(items, plan_id, plan_dims, plan_assessors, plan_assessed_units, plan_assessed_groups):
    """带模糊匹配的校验，返回丰富错误结构用于前端展示。
    返回: (valid_tasks, row_errors)
    valid_tasks: [(row_idx, item_dict, task_dict), ...]
    row_errors: [(row_idx, item_dict, [error_dict]), ...]
    error_dict: {field, type, message, suggestion, suggestion_id, auto_fixable}
    """
    valid_tasks = []
    row_errors = []
    CATEGORY_KEYWORDS = ["个街道", "个部门", "个乡镇", "个乡镇街道", "各单位", "部分中央", "中小学校", "人民团体", "中央在黔"]

    FIELD_LABEL = {"unit": "被考核单位", "dimension": "维度", "assessor": "评价部门",
                   "key_work": "重点工作", "main_task": "主要任务", "period": "晾晒周期"}

    def _err(field, etype, message, suggestion=None, suggestion_id=None, auto_fixable=False):
        return {"field": field, "type": etype, "message": message,
                "suggestion": suggestion, "suggestion_id": suggestion_id,
                "auto_fixable": auto_fixable}

    for i, item in enumerate(items, 2):
        unit_name = item.get("unit", "")
        dim_name = item.get("dimension", "")
        assessor_name = item.get("assessor", "")
        key_work = item.get("key_work", "").strip()
        main_task = item.get("main_task", "").strip()
        scoring_note = item.get("scoring_note", "").strip()
        period = _normalize_period(item.get("period", ""))

        item_copy = dict(item)  # 保留原始数据用于前端展示
        item_copy["period"] = period

        # 跳过无序号且全部关键字段为空的行
        seq = str(item.get("seq", ""))
        if seq and not seq.isdigit():
            if not any([unit_name, dim_name, assessor_name, key_work, main_task]):
                continue

        errors = []

        # --- 单位为空 ---
        if not unit_name:
            errors.append(_err("unit", "empty_unit", "被考核单位为空"))
            row_errors.append((i, item_copy, errors))
            continue

        # --- 必填项为空 ---
        missing = []
        if not dim_name: missing.append("维度")
        if not assessor_name: missing.append("评价部门")
        if not key_work: missing.append("重点工作")
        if not main_task: missing.append("主要任务")
        if missing:
            for m in missing:
                field_map = {"维度": "dimension", "评价部门": "assessor", "重点工作": "key_work", "主要任务": "main_task"}
                errors.append(_err(field_map[m], "empty_required", f"必填项为空：{m}"))
            row_errors.append((i, item_copy, errors))
            continue

        # --- 维度匹配（模糊） ---
        dim, dim_err, dim_suggestion, dim_sid = _find_dim_in_set_fuzzy(dim_name, plan_dims)
        if not dim:
            errors.append(_err("dimension", "dimension_not_found", dim_err,
                               dim_suggestion, dim_sid, auto_fixable=bool(dim_suggestion)))
            row_errors.append((i, item_copy, errors))
            continue
        elif dim_suggestion:
            # 模糊匹配成功但非精确匹配 → 警告，需人工确认
            errors.append(_err("dimension", "dimension_fuzzy",
                               f"维度「{dim_name}」可能与「{dim_suggestion}」匹配，请确认",
                               dim_suggestion, dim_sid, auto_fixable=True))

        # --- 评价部门匹配（模糊） ---
        assessor, assessor_err, assessor_suggestion, assessor_sid = _find_unit_in_set_fuzzy(assessor_name, plan_assessors)
        if not assessor:
            errors.append(_err("assessor", "assessor_not_found", f"评价部门{assessor_err}",
                               assessor_suggestion, assessor_sid, auto_fixable=bool(assessor_suggestion)))
            row_errors.append((i, item_copy, errors))
            continue
        elif assessor_suggestion:
            # 模糊匹配成功但非精确匹配 → 警告，需人工确认
            errors.append(_err("assessor", "assessor_fuzzy",
                               f"评价部门「{assessor_name}」可能与「{assessor_suggestion}」匹配，请确认",
                               assessor_suggestion, assessor_sid, auto_fixable=True))

        # --- 被考核单位展开 ---
        target_units = []

        if any(kw in unit_name for kw in CATEGORY_KEYWORDS):
            expanded, cat_err = _expand_category_units(unit_name, plan_assessed_groups)
            if cat_err:
                errors.append(_err("unit", "expand_failed", cat_err))
                row_errors.append((i, item_copy, errors))
                continue
            if expanded:
                target_units = [(u, None) for u in expanded]

        if not target_units:
            unit_names = _split_unit_names(unit_name)
            if not unit_names:
                errors.append(_err("unit", "empty_unit", "被考核单位为空"))
                row_errors.append((i, item_copy, errors))
                continue
            for uname in unit_names:
                u, u_err, u_suggestion, u_sid = _find_unit_in_set_fuzzy(uname, plan_assessed_units)
                if not u:
                    errors.append(_err("unit", "unit_not_found", u_err if u_err else f"单位「{uname}」不在方案预设中",
                                       u_suggestion, u_sid, auto_fixable=bool(u_suggestion)))
                else:
                    target_units.append((u, None))
                    if u_suggestion:
                        # 模糊匹配成功但非精确匹配 → 警告，需人工确认
                        errors.append(_err("unit", "unit_fuzzy",
                                           f"单位「{uname}」可能与「{u_suggestion}」匹配，请确认",
                                           u_suggestion, u_sid, auto_fixable=True))

        if errors:
            row_errors.append((i, item_copy, errors))
            continue

        if not target_units:
            errors.append(_err("unit", "unit_not_found", "无法解析被考核单位"))
            row_errors.append((i, item_copy, errors))
            continue

        # --- 生成任务 ---
        main_items, main_split = _split_numbered_items(main_task)
        score_items, score_split = _split_numbered_items(scoring_note)

        task_dicts = []
        if main_split:
            for idx, mt in enumerate(main_items):
                sn = score_items[idx] if score_split and idx < len(score_items) else scoring_note
                for unit, _ in target_units:
                    task_dicts.append({
                        "plan_id": plan_id,
                        "assessment_dimension_id": dim.id,
                        "unit_id": unit.id,
                        "assessor_unit_id": assessor.id,
                        "key_work": key_work,
                        "main_task": mt,
                        "scoring_note": sn,
                        "review_period": period,
                    })
        else:
            for unit, _ in target_units:
                task_dicts.append({
                    "plan_id": plan_id,
                    "assessment_dimension_id": dim.id,
                    "unit_id": unit.id,
                    "assessor_unit_id": assessor.id,
                    "key_work": key_work,
                    "main_task": main_task,
                    "scoring_note": scoring_note,
                    "review_period": period,
                })

        if task_dicts:
            valid_tasks.append((i, item_copy, task_dicts))

    return valid_tasks, row_errors


def _parse_import_files(files, plan):
    """解析所有上传文件，返回结构化数据用于校验。
    返回: (parsed_files, file_errors)
    parsed_files: [{filename, sheets: [{name, col_mapping, items}]}]
    file_errors: [(filename, sheet_name, row_idx, error_msg)]
    """
    parsed_files = []
    file_errors = []

    for file in files:
        filename = file.filename or "unknown.xlsx"
        file_bytes = file.read()
        wb_data = read_workbook(file_bytes, filename)

        if wb_data is None:
            file_errors.append((filename, "", 0, "无法读取文件，请确认文件格式正确"))
            continue
        if isinstance(wb_data, tuple):
            file_errors.append((filename, "", 0, wb_data[1]))
            continue

        file_sheets = []
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
                file_errors.append((filename, sname, 0, "未识别到表头行，请确认表头包含：评价部门、维度、重点工作、主要任务等"))
                continue

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

            file_sheets.append({
                "name": sname,
                "col_mapping": col_mapping,
                "header_row_idx": header_row_idx,
                "items": items,
            })

        if file_sheets:
            parsed_files.append({"filename": filename, "sheets": file_sheets})

    return parsed_files, file_errors


@task_bp.route("/api/tasks/import/preview", methods=["POST"])
@jwt_required()
def import_tasks_preview():
    """预览导入：校验全部文件，返回结构化 JSON（含错误+建议修正值），不写入数据库"""
    files = request.files.getlist("files")
    if not files:
        single = request.files.get("file")
        if single:
            files = [single]
        else:
            return jsonify({"msg": "请上传文件"}), 400

    plan_id = request.form.get("plan_id", type=int)
    if not plan_id:
        return jsonify({"msg": "请指定考核方案"}), 400

    plan = Plan.query.get(plan_id)
    if not plan:
        return jsonify({"msg": "方案不存在"}), 404

    # 构建方案预设字典
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
        return jsonify({"msg": f"方案「{plan.name}」没有预设考核维度"}), 400
    if not plan_assessors:
        return jsonify({"msg": f"方案「{plan.name}」没有设置主考单位"}), 400
    if not plan_assessed_units:
        return jsonify({"msg": f"方案「{plan.name}」没有被考核分组"}), 400

    parsed_files, file_errors = _parse_import_files(files, plan)

    # 汇总所有行
    total_rows = 0
    error_rows_count = 0
    result_files = []

    for pf in parsed_files:
        result_sheets = []
        for sheet in pf["sheets"]:
            valid_tasks, row_errors = _validate_import_rows_fuzzy(
                sheet["items"], plan_id, plan_dims, plan_assessors, plan_assessed_units, plan.assessed_groups,
            )
            total_rows += len(sheet["items"])

            # 构建带错误信息的行数据
            error_items = {ri: (item, errs) for ri, item, errs in row_errors}
            valid_items = {ri: item for ri, item, _ in valid_tasks}
            rows = []

            for idx, item in enumerate(sheet["items"], 2):
                if idx in error_items:
                    item_data, errs = error_items[idx]
                    rows.append({"row_idx": idx, "original": item_data, "errors": errs})
                    error_rows_count += 1
                elif idx in valid_items:
                    rows.append({"row_idx": idx, "original": valid_items[idx], "errors": []})
                else:
                    rows.append({"row_idx": idx, "original": item, "errors": []})

            result_sheets.append({
                "sheet_name": sheet["name"],
                "col_mapping": sheet["col_mapping"],
                "rows": rows,
            })

        result_files.append({"filename": pf["filename"], "sheets": result_sheets})

    # 文件级错误（如无法读取）
    for fname, sname, ridx, msg in file_errors:
        # find or create file entry
        file_entry = next((f for f in result_files if f["filename"] == fname), None)
        if not file_entry:
            file_entry = {"filename": fname, "sheets": []}
            result_files.append(file_entry)
        sheet_entry = next((s for s in file_entry["sheets"] if s["sheet_name"] == str(sname)), None)
        if not sheet_entry:
            sheet_entry = {"sheet_name": str(sname) if sname else fname, "col_mapping": {}, "rows": []}
            file_entry["sheets"].append(sheet_entry)
        sheet_entry["rows"].append({"row_idx": ridx, "original": {}, "errors": [
            {"field": "file", "type": "file_error", "message": msg, "suggestion": None, "suggestion_id": None, "auto_fixable": False}
        ]})
        error_rows_count += 1

    # 统计自动可修正数
    auto_fixable_count = 0
    unfixable_count = 0
    for f in result_files:
        for s in f["sheets"]:
            for row in s["rows"]:
                for e in row["errors"]:
                    if e["auto_fixable"]:
                        auto_fixable_count += 1
                    else:
                        unfixable_count += 1

    error_types = {}
    for f in result_files:
        for s in f["sheets"]:
            for row in s["rows"]:
                for e in row["errors"]:
                    t = e["type"]
                    error_types[t] = error_types.get(t, 0) + 1

    return jsonify({"data": {
        "plan_id": plan_id,
        "plan_name": plan.name,
        "total_rows": total_rows,
        "error_rows": error_rows_count,
        "auto_fixable": auto_fixable_count,
        "unfixable": unfixable_count,
        "error_types": error_types,
        "files": result_files,
    }})


@task_bp.route("/api/tasks/import/validate-field", methods=["POST"])
@jwt_required()
def import_validate_field():
    """校验单个字段值是否能在方案预设中匹配（仅精确匹配，模糊匹配不通过）。
    支持分隔符拆分：如 '单位A、单位B' 会拆分后逐个精确匹配。"""
    data = request.get_json()
    if not data:
        return jsonify({"valid": False, "message": "请提供校验数据"}), 400

    plan_id = data.get("plan_id")
    field = data.get("field", "").strip()
    value = data.get("value", "").strip()
    if not plan_id or not field or not value:
        return jsonify({"valid": False, "message": "参数不完整"}), 400

    plan = Plan.query.get(plan_id)
    if not plan:
        return jsonify({"valid": False, "message": "方案不存在"}), 404

    # 构建候选字典
    if field == "dimension":
        candidates = {}
        for ed in plan.evaluation_dimensions:
            for dim in ed.assessment_dimensions:
                candidates[dim.id] = dim
    elif field == "assessor":
        candidates = {u.id: u for u in plan.assessor_units}
    elif field == "unit":
        candidates = {}
        for g in plan.assessed_groups:
            for u in g.units:
                candidates[u.id] = u
    else:
        return jsonify({"valid": False, "message": f"不支持的字段类型：{field}"}), 400

    # 按分隔符拆分（保留括号内容），然后逐个精确匹配
    sub_names = _split_unit_names(value)
    if not sub_names:
        sub_names = [value]

    matched = []
    unmatched = []
    for sub in sub_names:
        sub = sub.strip()
        if not sub:
            continue
        obj, err = _exact_match_name(sub, candidates)
        if obj:
            matched.append({"name": obj.name, "id": obj.id})
        else:
            # 精确匹配失败，尝试模糊匹配给出建议
            suggestion = None
            suggestion_id = None
            if field == "dimension":
                _, _, sug, sid = _find_dim_in_set_fuzzy(sub, candidates)
                suggestion, suggestion_id = sug, sid
            else:
                _, _, sug, sid = _find_unit_in_set_fuzzy(sub, candidates)
                suggestion, suggestion_id = sug, sid
            unmatched.append({
                "value": sub,
                "error": err,
                "suggestion": suggestion,
                "suggestion_id": suggestion_id,
            })

    if not unmatched:
        return jsonify({
            "valid": True,
            "matched": matched,
        })
    else:
        # 构建面向用户的错误消息
        parts = []
        for u in unmatched:
            msg = u["error"]
            if u.get("suggestion"):
                msg += f"，建议：{u['suggestion']}"
            parts.append(msg)
        return jsonify({
            "valid": False,
            "message": "；".join(parts),
            "matched": matched,
            "unmatched": unmatched,
        })


@task_bp.route("/api/tasks/import/confirm", methods=["POST"])
@jwt_required()
def import_tasks_confirm():
    """确认导入：接收已修正的任务数组（支持名称或ID），服务端解析后校验入库"""
    data = request.get_json()
    if not data:
        return jsonify({"msg": "请提供导入数据"}), 400

    plan_id = data.get("plan_id")
    tasks = data.get("tasks", [])
    if not plan_id:
        return jsonify({"msg": "请指定考核方案"}), 400
    if not tasks:
        return jsonify({"msg": "没有可导入的任务"}), 400

    plan = Plan.query.get(plan_id)
    if not plan:
        return jsonify({"msg": "方案不存在"}), 404

    # 构建方案预设字典（名称 → 对象）
    dim_by_name = {}
    for ed in plan.evaluation_dimensions:
        for dim in ed.assessment_dimensions:
            dim_by_name[dim.name] = dim
            dim_by_name[dim.id] = dim
    dim_by_name_fuzzy = {}  # 用于按名称查找
    for ed in plan.evaluation_dimensions:
        for dim in ed.assessment_dimensions:
            dim_by_name_fuzzy[_normalize_name(dim.name)] = dim

    assessor_by_name = {}
    for u in plan.assessor_units:
        assessor_by_name[u.name] = u
        assessor_by_name[u.id] = u
    assessor_by_name_fuzzy = {_normalize_name(u.name): u for u in plan.assessor_units}

    unit_by_name = {}
    for g in plan.assessed_groups:
        for u in g.units:
            unit_by_name[u.name] = u
            unit_by_name[u.id] = u
    unit_by_name_fuzzy = {_normalize_name(u.name): u for u in unit_by_name.values()}

    def _resolve_dim(t):
        """解析维度：优先用 ID，否则按名称匹配"""
        if t.get("assessment_dimension_id"):
            return dim_by_name.get(t["assessment_dimension_id"])
        name = t.get("dimension_name", "").strip()
        if name:
            obj, _ = _fuzzy_match_name(name, list(dim_by_name_fuzzy.values()), lambda d: d.name)
            return obj
        return None

    def _resolve_assessor(t):
        if t.get("assessor_unit_id"):
            return assessor_by_name.get(t["assessor_unit_id"])
        name = t.get("assessor_name", "").strip()
        if name:
            obj, _ = _fuzzy_match_name(name, list(assessor_by_name_fuzzy.values()), lambda u: u.name)
            return obj
        return None

    def _resolve_units(t):
        """解析被考核单位：支持分隔符拆分（逗号/顿号/分号），逐个子名称匹配。
        返回 (unit_objects_list, error_messages_list)
        """
        unit_name = t.get("unit_name", "").strip()
        if not unit_name:
            return [], ["被考核单位为空"]

        # 优先用 ID 直接查找
        if t.get("unit_id"):
            u = unit_by_name.get(t["unit_id"])
            if u:
                return [u], []
            # ID 查找失败，回退到名称匹配

        # 按分隔符拆分单位名称（与 _validate_import_rows_fuzzy 一致）
        unit_names = _split_unit_names(unit_name)
        if not unit_names:
            return [], ["无法解析被考核单位"]

        resolved = []
        errors = []
        for uname in unit_names:
            uname = uname.strip()
            if not uname:
                continue
            obj, _ = _fuzzy_match_name(uname, list(unit_by_name_fuzzy.values()), lambda u: u.name)
            if obj:
                if obj not in resolved:
                    resolved.append(obj)
            else:
                errors.append(f"单位「{uname}」不在方案预设中")

        if not resolved and not errors:
            errors.append(f"无法解析被考核单位「{unit_name}」")
        return resolved, errors

    # 全量校验：任一任务无法解析则整批驳回，返回详细错误
    resolution_errors = []
    resolved_tasks = []

    for i, t in enumerate(tasks):
        dim = _resolve_dim(t)
        assessor = _resolve_assessor(t)
        units, unit_errors = _resolve_units(t)

        task_errors = []
        if not dim:
            task_errors.append({"field": "dimension", "value": t.get("dimension_name", ""), "msg": "维度无法解析，不在方案预设中"})
        if not assessor:
            task_errors.append({"field": "assessor", "value": t.get("assessor_name", ""), "msg": "评价部门无法解析，不在方案预设中"})
        if unit_errors:
            for ue in unit_errors:
                task_errors.append({"field": "unit", "value": t.get("unit_name", ""), "msg": ue})
        if not units:
            task_errors.append({"field": "unit", "value": t.get("unit_name", ""), "msg": "被考核单位无法解析，不在方案预设中"})
        if not t.get("key_work") or not t.get("main_task"):
            task_errors.append({"field": "required", "value": "", "msg": "重点工作或主要任务为空"})

        if task_errors:
            resolution_errors.append({"index": i, "errors": task_errors,
                                       "dimension_name": t.get("dimension_name", ""),
                                       "unit_name": t.get("unit_name", ""),
                                       "assessor_name": t.get("assessor_name", ""),
                                       "key_work": t.get("key_work", "")})
        else:
            for unit in units:
                resolved_tasks.append((dim, assessor, unit, t))

    if resolution_errors:
        return jsonify({
            "msg": f"{len(resolution_errors)} 个任务无法解析，请修正后重新提交",
            "errors": resolution_errors,
            "total": len(tasks),
            "resolvable": len(resolved_tasks),
        }), 400

    # 全部通过校验，批量入库（含编号拆分）
    created_count = 0
    for dim, assessor, unit, t in resolved_tasks:
        key_work = t.get("key_work", "")
        main_task = t.get("main_task", "")
        scoring_note = t.get("scoring_note", "")
        review_period = t.get("review_period", "月度")
        status = t.get("status", "pending")

        # 拆分主要任务中的编号列表（与原 import 端点行为一致）
        main_items, main_split = _split_numbered_items(main_task)
        score_items, score_split = _split_numbered_items(scoring_note)

        if main_split:
            for idx, mt in enumerate(main_items):
                sn = score_items[idx] if score_split and idx < len(score_items) else scoring_note
                db.session.add(Task(
                    plan_id=plan_id,
                    assessment_dimension_id=dim.id,
                    unit_id=unit.id,
                    assessor_unit_id=assessor.id,
                    key_work=key_work,
                    main_task=mt,
                    scoring_note=sn,
                    review_period=review_period,
                    status=status,
                ))
                created_count += 1
        else:
            db.session.add(Task(
                plan_id=plan_id,
                assessment_dimension_id=dim.id,
                unit_id=unit.id,
                assessor_unit_id=assessor.id,
                key_work=key_work,
                main_task=main_task,
                scoring_note=scoring_note,
                review_period=review_period,
                status=status,
            ))
            created_count += 1

    db.session.commit()

    return jsonify({
        "msg": f"成功导入 {created_count} 个任务（来自 {len(tasks)} 条提交数据）",
        "data": {"created": created_count},
    })


@task_bp.route("/api/tasks/import", methods=["POST"])
@jwt_required()
def import_tasks():
    # 支持多文件批量导入（files[]），向后兼容旧单文件 key（file）
    files = request.files.getlist("files")
    if not files:
        single = request.files.get("file")
        if single:
            files = [single]
        else:
            return jsonify({"msg": "请上传文件"}), 400

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

    # ========== 第一阶段：全量校验所有文件 ==========
    all_valid_tasks = []       # [(filename, sheet_name, row_idx, task_dict), ...]
    all_row_errors = []        # [(filename, sheet_name, row_idx, error_msg), ...]
    file_items_map = {}        # {filename: {sheet_name: [(row_idx, item_dict), ...]}}
    file_col_mapping = {}      # {filename: {sheet_name: col_mapping}}
    processed_files = []       # [filename, ...] 按处理顺序

    for file in files:
        filename = file.filename or "unknown.xlsx"
        file_bytes = file.read()

        wb_data = read_workbook(file_bytes, filename)
        if wb_data is None:
            all_row_errors.append((filename, "", 0, "无法读取文件，请确认文件格式正确"))
            continue
        if isinstance(wb_data, tuple):
            all_row_errors.append((filename, "", 0, wb_data[1]))
            continue

        processed_files.append(filename)
        if filename not in file_items_map:
            file_items_map[filename] = {}
        if filename not in file_col_mapping:
            file_col_mapping[filename] = {}

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
                all_row_errors.append((filename, sname, 0, "未识别到表头行，请确认表头包含：评价部门、维度、重点工作、主要任务等"))
                continue

            file_col_mapping[filename][sname] = col_mapping

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

            file_items_map[filename][sname] = [(header_row_idx + 2 + idx, item) for idx, item in enumerate(items)]

            valid_tasks, row_errors = _validate_import_rows(items, plan_id, plan_dims, plan_assessors, plan_assessed_units, plan.assessed_groups)
            all_valid_tasks.extend([(filename, sname, idx, t) for idx, t in valid_tasks])
            all_row_errors.extend([(filename, sname, idx, msg) for idx, msg in row_errors])

    # ========== 有错误：生成单一错误报告 Excel（覆盖所有文件）==========
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
        first_mapping = None
        for fname in processed_files:
            for smap in file_col_mapping.get(fname, {}).values():
                first_mapping = smap
                break
            if first_mapping:
                break
        if not first_mapping:
            first_mapping = {}
        ordered_fields = [k for k in data_fields if k in first_mapping]
        for k in first_mapping:
            if k not in ordered_fields:
                ordered_fields.append(k)
        detail_headers = ["导入文件"] + ["原行号"] + ordered_fields + ["错误说明"]

        # 按文件 → sheet → row 三级分组错误
        errors_by_file = {}  # {filename: {sheet_name: {row_idx: [msgs]}}}
        for fname, sname, row_idx, msg in all_row_errors:
            if fname not in errors_by_file:
                errors_by_file[fname] = {}
            if sname not in errors_by_file[fname]:
                errors_by_file[fname][sname] = {}
            if row_idx not in errors_by_file[fname][sname]:
                errors_by_file[fname][sname][row_idx] = []
            errors_by_file[fname][sname][row_idx].append(msg)

        # 统计总错误工作表数（跨所有文件）
        total_error_sheets = sum(len(sheets) for sheets in errors_by_file.values())
        total_error_files = len(errors_by_file)
        total_sheets_imported = 0
        for fname in processed_files:
            total_sheets_imported += len(file_items_map.get(fname, {}))

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

        file_names_list = "、".join(processed_files)
        summary_items = [
            ("导入方案", plan.name),
            ("导入文件数", f"{len(processed_files)} 个"),
            ("导入文件", file_names_list),
            ("导入工作表数", f"{total_sheets_imported} 个"),
            ("错误文件数", f"{total_error_files} 个"),
            ("错误工作表数", f"{total_error_sheets} 个"),
            ("总错误条数", f"{len(all_row_errors)} 条"),
        ]
        for label, value in summary_items:
            ws_summary.cell(row=row, column=1, value=label).font = header_font
            ws_summary.cell(row=row, column=2, value=value).font = normal_font
            row += 1

        row += 1
        # 各文件错误分布
        ws_summary.cell(row=row, column=1, value="各文件错误分布").font = header_font
        row += 1
        dist_headers = ["文件名称", "工作表", "错误行数", "详细说明"]
        for ci, h in enumerate(dist_headers, 1):
            cell = ws_summary.cell(row=row, column=ci, value=h)
            cell.font = header_font
            cell.alignment = center_align
            cell.border = thin_border
            cell.fill = header_fill
        ws_summary.column_dimensions['C'].width = 14
        ws_summary.column_dimensions['D'].width = 55
        row += 1

        for fname in processed_files:
            file_sheets = errors_by_file.get(fname, {})
            if not file_sheets:
                # 文件级别错误（如无法读取）
                for _fname, _sname, _ridx, msg in all_row_errors:
                    if _fname == fname and not _sname:
                        ws_summary.cell(row=row, column=1, value=fname).font = normal_font
                        ws_summary.cell(row=row, column=2, value="-").font = normal_font
                        ws_summary.cell(row=row, column=3, value="1 行").font = normal_font
                        ws_summary.cell(row=row, column=4, value=msg).font = Font(name="仿宋", size=11, color="FF0000")
                        for ci in range(1, 5):
                            ws_summary.cell(row=row, column=ci).border = thin_border
                            ws_summary.cell(row=row, column=ci).alignment = center_align
                        row += 1
                continue

            for sname, row_errs in file_sheets.items():
                ws_summary.cell(row=row, column=1, value=fname).font = normal_font
                ws_summary.cell(row=row, column=2, value=sname).font = normal_font
                ws_summary.cell(row=row, column=3, value=f"{len(row_errs)} 行").font = normal_font
                # 汇总该 sheet 的所有错误类型
                error_types = {}
                for msgs in row_errs.values():
                    for m in msgs:
                        key = m.split("：")[0] if "：" in m else m
                        error_types[key] = error_types.get(key, 0) + 1
                error_summary = "；".join(f"{k}({v}处)" for k, v in error_types.items())
                ws_summary.cell(row=row, column=4, value=error_summary).font = normal_font
                for ci in range(1, 5):
                    ws_summary.cell(row=row, column=ci).border = thin_border
                    ws_summary.cell(row=row, column=ci).alignment = center_align
                row += 1

        row += 1
        ws_summary.cell(row=row, column=1, value="处理方式").font = header_font
        ws_summary.cell(row=row, column=2, value="以上问题导致全部数据未导入。请按各子表标记修正后，重新导入全部数据。").font = Font(name="仿宋", size=11, color="FF0000")
        row += 1
        ws_summary.cell(row=row, column=1, value="子表说明").font = header_font
        ws_summary.cell(row=row, column=2, value="后续各子表按原工作表分列错误明细，首列标注来源文件，含原始数据和具体错误原因，红色底色标记。").font = normal_font

        # ==================== 后续 Sheet：每个（文件, 工作表）一个错误明细子表 ====================
        for fname in processed_files:
            file_sheets = errors_by_file.get(fname, {})
            for sname, row_errs in file_sheets.items():
                safe_name = fname[:15] + "_" + sname[:12]
                safe_name = safe_name[:28]  # Excel sheet 名最多 31 字符
                ws_detail = wb.create_sheet(title=safe_name)

                # 表头（首列为"导入文件"）
                for ci, h in enumerate(detail_headers, 1):
                    cell = ws_detail.cell(row=1, column=ci, value=h)
                    cell.font = header_font
                    cell.alignment = center_align
                    cell.border = thin_border
                    cell.fill = header_fill
                ws_detail.column_dimensions['A'].width = 22
                ws_detail.column_dimensions['B'].width = 10
                for ci in range(3, len(detail_headers) + 1):
                    col_letter = chr(64 + ci) if ci <= 26 else 'A'
                    ws_detail.column_dimensions[col_letter].width = 16
                last_col_letter = chr(64 + len(detail_headers)) if len(detail_headers) <= 26 else 'A'
                ws_detail.column_dimensions[last_col_letter].width = 45

                detail_row = 2
                items = file_items_map.get(fname, {}).get(sname, [])
                for row_idx in sorted(row_errs.keys()):
                    msgs = row_errs[row_idx]
                    combined_msg = "；".join(msgs)

                    original_item = None
                    for idx, item in items:
                        if idx == row_idx:
                            original_item = item
                            break

                    ws_detail.cell(row=detail_row, column=1, value=fname).font = normal_font
                    ws_detail.cell(row=detail_row, column=2, value=row_idx).font = normal_font
                    ci = 3
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

                ws_detail.freeze_panes = "C2"

        # 将错误摘要移到第一个位置
        wb.move_sheet("错误摘要", offset=-total_error_sheets)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        return send_file(output,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         as_attachment=True,
                         download_name=f"考核任务导入错误报告_{plan.name}.xlsx")

    # ========== 无错误：全部入库 ==========
    for fname, sname, row_idx, task_dict in all_valid_tasks:
        db.session.add(Task(**task_dict))
    db.session.commit()

    return jsonify({
        "msg": f"全部校验通过，成功导入 {len(all_valid_tasks)} 个任务（来自 {len(processed_files)} 个文件）",
        "data": {"created": len(all_valid_tasks), "errors": 0, "files": len(processed_files)},
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


def _build_export_task_rows(tasks, include_unit=True):
    """将任务列表转为导出用的行数据"""
    headers = ["序号"]
    if include_unit:
        headers.append("被考核单位")
    headers += ["维度", "评价部门", "重点工作", "主要任务", "评分说明", "晾晒周期", "完成情况", "得分", "评语"]
    rows = []
    seq = 1
    for t in tasks:
        sub = t.submissions[-1].content if t.submissions else ""
        score_obj = t.scores[-1] if t.scores else None
        row = [seq]
        if include_unit:
            row.append(t.unit.name if t.unit else "")
        row += [
            t.assessment_dimension.name if t.assessment_dimension else "",
            t.assessor_unit.name if t.assessor_unit else "",
            t.key_work, t.main_task, t.scoring_note or "", t.review_period,
            sub, score_obj.score if score_obj else "", score_obj.comment if score_obj else "",
        ]
        rows.append(row)
        seq += 1
    return headers, rows


def _get_plan_year(plan_id):
    if plan_id:
        plan = Plan.query.get(plan_id)
        return str(plan.year) if plan else ""
    return ""


# ==================== 导出1：导出当前搜索结果 ====================

@task_bp.route("/api/tasks/export", methods=["GET"])
@jwt_required()
def export_tasks():
    """导出当前搜索结果（接受 list_tasks 全部筛选参数）"""
    user = _get_user(int(get_jwt_identity()))
    plan_id = request.args.get("plan_id", type=int)

    q = build_task_query(
        plan_id=plan_id,
        status=request.args.get("status", "").strip(),
        search=request.args.get("search", "").strip(),
        search_type=request.args.get("search_type", "all").strip(),
        assessor_unit_id=request.args.get("assessor_unit_id", "").strip(),
        unit_id=request.args.get("unit_id", "").strip(),
        dimension_ids=request.args.get("dimension_ids", "").strip(),
        key_works=request.args.get("key_works", "").strip(),
        period=request.args.get("period", "").strip(),
        user=user,
    )

    tasks = q.options(
        joinedload(Task.assessment_dimension),
        joinedload(Task.unit),
        joinedload(Task.assessor_unit),
        joinedload(Task.submissions),
        joinedload(Task.scores),
    ).join(AssessmentDimension, Task.assessment_dimension_id == AssessmentDimension.id)\
     .order_by(AssessmentDimension.name, Task.id).all()

    year = _get_plan_year(plan_id)
    title = f"{year}年度考核任务书" if year else "考核任务书"
    headers, rows = _build_export_task_rows(tasks, include_unit=True)
    output = export_gov_xlsx(title, headers, rows, merge_col=2 if True else 1)
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="考核任务书_搜索结果.xlsx")


# ==================== 导出2：单表全部数据 ====================

@task_bp.route("/api/tasks/export-all-single", methods=["GET"])
@jwt_required()
def export_all_single():
    """全部数据导出为单个 xlsx"""
    user = _get_user(int(get_jwt_identity()))
    plan_id = request.args.get("plan_id", type=int)

    q = build_task_query(plan_id=plan_id, user=user)

    tasks = q.options(
        joinedload(Task.assessment_dimension),
        joinedload(Task.unit),
        joinedload(Task.assessor_unit),
        joinedload(Task.submissions),
        joinedload(Task.scores),
    ).join(AssessmentDimension, Task.assessment_dimension_id == AssessmentDimension.id)\
     .order_by(AssessmentDimension.name, Task.id).all()

    year = _get_plan_year(plan_id)
    title = f"{year}年度考核任务书（全量）" if year else "考核任务书（全量）"
    headers, rows = _build_export_task_rows(tasks, include_unit=True)
    output = export_gov_xlsx(title, headers, rows, merge_col=2)
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="考核任务书_全量单表.xlsx")


# ==================== 导出3：按被考核单位分包 ZIP ====================


# ==================== 全量导出（按单位分包 ZIP） ====================

@task_bp.route("/api/tasks/export-all", methods=["GET"])
@jwt_required()
def export_all_tasks():
    user = _get_user(int(get_jwt_identity()))
    plan_id = request.args.get("plan_id", type=int)

    q = build_task_query(plan_id=plan_id, user=user)

    tasks = q.options(
        joinedload(Task.assessment_dimension),
        joinedload(Task.unit),
        joinedload(Task.assessor_unit),
        joinedload(Task.submissions),
        joinedload(Task.scores),
    ).join(AssessmentDimension, Task.assessment_dimension_id == AssessmentDimension.id)\
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
                     as_attachment=True, download_name="考核任务书_按被考核单位.zip")


# ==================== 导出4：按主考单位分包 ZIP ====================

@task_bp.route("/api/tasks/export-by-assessor", methods=["GET"])
@jwt_required()
def export_by_assessor():
    """全量导出，按主考单位分组，每个单位一个 xlsx，打包 ZIP"""
    user = _get_user(int(get_jwt_identity()))
    plan_id = request.args.get("plan_id", type=int)

    q = build_task_query(plan_id=plan_id, user=user)

    tasks = q.options(
        joinedload(Task.assessment_dimension),
        joinedload(Task.unit),
        joinedload(Task.assessor_unit),
        joinedload(Task.submissions),
        joinedload(Task.scores),
    ).join(AssessmentDimension, Task.assessment_dimension_id == AssessmentDimension.id)\
     .order_by(Task.assessor_unit_id, AssessmentDimension.name, Task.id).all()

    # 按主考单位分组
    assessor_tasks = {}
    for t in tasks:
        key = t.assessor_unit_id
        if key not in assessor_tasks:
            assessor_tasks[key] = {"name": t.assessor_unit.name if t.assessor_unit else "未分配", "tasks": []}
        assessor_tasks[key]["tasks"].append(t)

    year = _get_plan_year(plan_id)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for assessor_id, data in assessor_tasks.items():
            unit_name = data["name"]
            task_list = data["tasks"]

            title = f"{year}年度{unit_name}主考任务清单" if year else f"{unit_name}主考任务书"
            headers = ["序号", "被考核单位", "维度", "重点工作", "主要任务", "评分说明", "晾晒周期", "完成情况", "得分", "评语"]
            rows = []
            seq = 1
            for t in task_list:
                sub = t.submissions[-1].content if t.submissions else ""
                score_obj = t.scores[-1] if t.scores else None
                rows.append([
                    seq,
                    t.unit.name if t.unit else "",
                    t.assessment_dimension.name if t.assessment_dimension else "",
                    t.key_work, t.main_task, t.scoring_note or "", t.review_period,
                    sub, score_obj.score if score_obj else "", score_obj.comment if score_obj else "",
                ])
                seq += 1

            xlsx_buf = export_gov_xlsx(title, headers, rows, merge_col=1)
            safe_name = unit_name.replace("/", "_").replace("\\", "_")
            zf.writestr(f"{safe_name}主考.xlsx", xlsx_buf.getvalue())

    zip_buf.seek(0)
    return send_file(zip_buf, mimetype="application/zip",
                     as_attachment=True, download_name="考核任务书_按主考单位.zip")
