from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from models import db, Task, QualityIssue
from services.quality_checker import run_quality_check

qc_bp = Blueprint("quality_check", __name__)


def _issue_to_dict(i):
    return {
        "id": i.id, "plan_id": i.plan_id, "task_id": i.task_id,
        "issue_type": i.issue_type, "column_name": i.column_name,
        "text": i.text, "suggestion": i.suggestion, "context": i.context,
        "confidence": i.confidence, "status": i.status,
    }


@qc_bp.route("/api/quality-check/run", methods=["POST"])
@jwt_required()
def run_check():
    data = request.get_json() or {}
    plan_id = data.get("plan_id")
    if not plan_id:
        return jsonify({"msg": "请选择考核方案"}), 400
    results = run_quality_check(plan_id=plan_id)
    return jsonify({"data": results, "msg": f"检测完成，共发现 {results['total_issues']} 个问题"})


@qc_bp.route("/api/quality-check/issues", methods=["GET"])
@jwt_required()
def list_issues():
    plan_id = request.args.get("plan_id", type=int)
    status = request.args.get("status", "")
    issue_type = request.args.get("issue_type", "")
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 100, type=int)
    page_size = min(page_size, 500)

    q = QualityIssue.query
    if plan_id:
        q = q.filter(QualityIssue.plan_id == plan_id)
    if status:
        q = q.filter(QualityIssue.status == status)
    if issue_type:
        q = q.filter(QualityIssue.issue_type.contains(issue_type))

    total = q.count()
    items = q.order_by(QualityIssue.id).offset((page - 1) * page_size).limit(page_size).all()
    return jsonify({"data": {
        "items": [_issue_to_dict(i) for i in items],
        "total": total, "page": page, "page_size": page_size,
    }})


@qc_bp.route("/api/quality-check/issues/<int:issue_id>", methods=["PUT"])
@jwt_required()
def update_issue(issue_id):
    i = QualityIssue.query.get(issue_id)
    if not i:
        return jsonify({"msg": "问题不存在"}), 404
    data = request.get_json() or {}
    if "status" in data:
        i.status = data["status"]
    db.session.commit()
    return jsonify({"msg": "更新成功"})


@qc_bp.route("/api/quality-check/issues/batch-status", methods=["POST"])
@jwt_required()
def batch_update_status():
    data = request.get_json() or {}
    ids = data.get("ids", [])
    status = data.get("status", "")
    if not ids or not status:
        return jsonify({"msg": "参数错误"}), 400
    QualityIssue.query.filter(QualityIssue.id.in_(ids)).update({"status": status}, synchronize_session=False)
    db.session.commit()
    return jsonify({"msg": f"已更新 {len(ids)} 条问题"})


@qc_bp.route("/api/quality-check/batch-correct", methods=["POST"])
@jwt_required()
def batch_correct():
    """更正任务字段，同步更新同 assessor + 同 key_work 原值的所有任务"""
    data = request.get_json() or {}
    task_id = data.get("task_id")
    field = data.get("field")   # key_work / main_task / scoring_note
    new_value = data.get("new_value", "")
    if not task_id or not field:
        return jsonify({"msg": "参数错误"}), 400

    task = Task.query.get(task_id)
    if not task:
        return jsonify({"msg": "任务不存在"}), 404

    old_value = getattr(task, field, "")
    plan_id = task.plan_id
    assessor_id = task.assessor_unit_id

    # 查找同一方案、同一评价部门、同一原值的所有任务
    siblings = Task.query.filter(
        Task.plan_id == plan_id,
        Task.assessor_unit_id == assessor_id,
        getattr(Task, field) == old_value,
    ).all()

    updated = 0
    for t in siblings:
        setattr(t, field, new_value)
        updated += 1

    # 标记相关质检问题为已修复
    QualityIssue.query.filter(
        QualityIssue.task_id.in_([t.id for t in siblings]),
        QualityIssue.column_name == _field_label(field),
    ).update({"status": "resolved"}, synchronize_session=False)

    db.session.commit()
    return jsonify({"msg": f"已更正 {updated} 条任务，涉及 {len(set(t.unit_id for t in siblings))} 个单位"})


def _field_label(field):
    return {"key_work": "重点工作", "main_task": "主要任务", "scoring_note": "评分说明"}.get(field, field)
