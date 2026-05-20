from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from models import db, Plan, EvaluationDimension, AssessmentDimension, AssessedGroup, GroupDimensionWeight, Unit, Organization
from datetime import datetime

plan_bp = Blueprint("plan", __name__)


# ==================== 考核方案 CRUD ====================

@plan_bp.route("/api/plans", methods=["GET"])
@jwt_required()
def list_plans():
    search = request.args.get("search", "").strip()
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    page_size = min(page_size, 100)

    q = Plan.query
    if search:
        q = q.filter(Plan.name.contains(search))

    total = q.count()
    plans = q.order_by(Plan.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    data = []
    for p in plans:
        data.append({
            "id": p.id,
            "name": p.name,
            "year": p.year,
            "start_date": str(p.start_date),
            "end_date": str(p.end_date),
            "created_date": str(p.created_date),
            "status": p.status,
            "assessor_unit_count": len(p.assessor_units),
            "group_count": len(p.assessed_groups),
        })
    return jsonify({"data": {"items": data, "total": total, "page": page, "page_size": page_size}})


@plan_bp.route("/api/plans/<int:plan_id>", methods=["GET"])
@jwt_required()
def get_plan(plan_id):
    p = Plan.query.get(plan_id)
    if not p:
        return jsonify({"msg": "方案不存在"}), 404

    # 评价维度
    dims = []
    for d in p.evaluation_dimensions:
        ad = [{"id": a.id, "name": a.name, "sort_order": a.sort_order}
              for a in d.assessment_dimensions]
        dims.append({"id": d.id, "name": d.name, "score": d.score, "is_actual_assessment": d.is_actual_assessment, "assessment_dimensions": ad})

    # 主考单位
    assessor_units = [{"id": u.id, "name": u.name, "org_name": u.organization.name if u.organization else ""} for u in p.assessor_units]

    # 被考核分组
    groups = []
    for g in p.assessed_groups:
        gu = [{"id": u.id, "name": u.name, "org_name": u.organization.name if u.organization else ""} for u in g.units]
        gw = [{"assessment_dimension_id": gw.assessment_dimension_id, "weight": gw.weight,
               "dimension_name": gw.assessment_dimension.name if gw.assessment_dimension else ""} for gw in g.dimension_weights]
        groups.append({"id": g.id, "name": g.name, "units": gu, "dimension_weights": gw})

    return jsonify({"data": {
        "id": p.id, "name": p.name, "year": p.year,
        "start_date": str(p.start_date), "end_date": str(p.end_date),
        "created_date": str(p.created_date), "status": p.status,
        "evaluation_dimensions": dims,
        "assessor_units": assessor_units,
        "assessed_groups": groups,
    }})


@plan_bp.route("/api/plans", methods=["POST"])
@jwt_required()
def create_plan():
    data = request.get_json()
    name = data.get("name", "").strip()
    year = data.get("year")
    start_date = data.get("start_date")
    end_date = data.get("end_date")

    if not name:
        return jsonify({"msg": "方案名称不能为空"}), 400
    if not year:
        return jsonify({"msg": "考核年度不能为空"}), 400
    if not start_date or not end_date:
        return jsonify({"msg": "起止时间不能为空"}), 400

    plan = Plan(
        name=name, year=int(year),
        start_date=datetime.strptime(start_date, "%Y-%m-%d").date(),
        end_date=datetime.strptime(end_date, "%Y-%m-%d").date(),
        created_date=datetime.utcnow().date(),
    )
    db.session.add(plan)
    db.session.flush()

    # 自动创建"单位实际考核"评价维度（分值100分，等后续添加其他维度再调整）
    dim = EvaluationDimension(name="单位实际考核", score=100, is_actual_assessment=True, plan_id=plan.id)
    db.session.add(dim)

    db.session.commit()
    return jsonify({"data": {"id": plan.id}, "msg": "创建成功"})


@plan_bp.route("/api/plans/<int:plan_id>", methods=["PUT"])
@jwt_required()
def update_plan(plan_id):
    plan = Plan.query.get(plan_id)
    if not plan:
        return jsonify({"msg": "方案不存在"}), 404

    data = request.get_json()
    if data.get("name"):
        plan.name = data["name"].strip()
    if data.get("year"):
        plan.year = int(data["year"])
    if data.get("start_date"):
        plan.start_date = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
    if data.get("end_date"):
        plan.end_date = datetime.strptime(data["end_date"], "%Y-%m-%d").date()

    db.session.commit()
    return jsonify({"msg": "编辑成功"})


@plan_bp.route("/api/plans/<int:plan_id>", methods=["DELETE"])
@jwt_required()
def delete_plan(plan_id):
    plan = Plan.query.get(plan_id)
    if not plan:
        return jsonify({"msg": "方案不存在"}), 404

    from models import TaskScore, TaskSubmission, Task, GroupDimensionWeight, AssessedGroup, \
        AssessmentDimension, EvaluationDimension, plan_unit

    # 按依赖顺序逐层删除，确保不触发 FK 约束问题
    task_ids = [r[0] for r in Task.query.with_entities(Task.id).filter_by(plan_id=plan_id).all()]
    if task_ids:
        TaskScore.query.filter(TaskScore.task_id.in_(task_ids)).delete(synchronize_session=False)
        TaskSubmission.query.filter(TaskSubmission.task_id.in_(task_ids)).delete(synchronize_session=False)
        Task.query.filter(Task.id.in_(task_ids)).delete(synchronize_session=False)

    for g in plan.assessed_groups:
        GroupDimensionWeight.query.filter_by(group_id=g.id).delete(synchronize_session=False)
    AssessedGroup.query.filter_by(plan_id=plan_id).delete(synchronize_session=False)

    for d in plan.evaluation_dimensions:
        AssessmentDimension.query.filter_by(evaluation_dimension_id=d.id).delete(synchronize_session=False)
    EvaluationDimension.query.filter_by(plan_id=plan_id).delete(synchronize_session=False)

    # 解除主考单位关联
    db.session.execute(plan_unit.delete().where(plan_unit.c.plan_id == plan_id))

    db.session.delete(plan)
    db.session.commit()
    return jsonify({"msg": "删除成功"})


@plan_bp.route("/api/plans/<int:plan_id>/issue", methods=["POST"])
@jwt_required()
def issue_plan(plan_id):
    plan = Plan.query.get(plan_id)
    if not plan:
        return jsonify({"msg": "方案不存在"}), 404

    # 校验：至少有一个主考单位和被考核分组
    if not plan.assessor_units:
        return jsonify({"msg": "请添加主考单位"}), 400
    if not plan.assessed_groups:
        return jsonify({"msg": "请创建被考核分组"}), 400

    # 校验所有评价维度分值合计=100
    total = sum(d.score for d in plan.evaluation_dimensions)
    if abs(total - 100) > 0.01:
        return jsonify({"msg": f"评价维度分值合计为{total}，应为100"}), 400

    plan.status = "issued"
    db.session.commit()
    return jsonify({"msg": "下发成功"})


# ==================== 评价维度 ====================

def _sync_actual_assessment_score(plan_id):
    """单位实际考核分值 = 100 - 其他评价维度分值合计"""
    dims = EvaluationDimension.query.filter_by(plan_id=plan_id).all()
    actual = next((d for d in dims if d.is_actual_assessment), None)
    if not actual:
        return
    other_total = sum(d.score for d in dims if not d.is_actual_assessment)
    actual.score = max(1, 100 - other_total)
    db.session.commit()


@plan_bp.route("/api/plans/<int:plan_id>/dimensions", methods=["POST"])
@jwt_required()
def add_dimension(plan_id):
    plan = Plan.query.get(plan_id)
    if not plan:
        return jsonify({"msg": "方案不存在"}), 404

    data = request.get_json()
    name = data.get("name", "").strip()
    score = data.get("score")

    if not name:
        return jsonify({"msg": "维度名称不能为空"}), 400
    if not score or float(score) <= 0:
        return jsonify({"msg": "分值必须大于0"}), 400

    score_f = float(score)
    other_total = sum(d.score for d in plan.evaluation_dimensions if not d.is_actual_assessment)
    if other_total + score_f > 99:
        return jsonify({"msg": f"分值超限：其他维度合计{other_total}分，剩余{100 - other_total}分可用"}), 400

    dim = EvaluationDimension(name=name, score=score_f, plan_id=plan_id)
    db.session.add(dim)
    db.session.flush()
    _sync_actual_assessment_score(plan_id)
    return jsonify({"msg": "添加成功"})


@plan_bp.route("/api/dimensions/<int:dim_id>", methods=["PUT"])
@jwt_required()
def update_dimension(dim_id):
    dim = EvaluationDimension.query.get(dim_id)
    if not dim:
        return jsonify({"msg": "维度不存在"}), 404

    data = request.get_json()
    if data.get("name"):
        dim.name = data["name"].strip()
    if data.get("score") is not None:
        new_score = float(data["score"])
        if new_score <= 0:
            return jsonify({"msg": "分值必须大于0"}), 400
        # 只允许修改非单位实际考核的维度分值
        if dim.is_actual_assessment:
            return jsonify({"msg": "单位实际考核分值自动计算，不可手动修改"}), 400
        other_total = sum(d.score for d in EvaluationDimension.query.filter_by(plan_id=dim.plan_id).all() if not d.is_actual_assessment and d.id != dim.id)
        if other_total + new_score > 99:
            return jsonify({"msg": f"分值超限：其他维度合计{other_total}分，剩余{100 - other_total}分可用"}), 400
        dim.score = new_score

    db.session.commit()
    _sync_actual_assessment_score(dim.plan_id)
    return jsonify({"msg": "编辑成功"})


@plan_bp.route("/api/dimensions/<int:dim_id>", methods=["DELETE"])
@jwt_required()
def delete_dimension(dim_id):
    dim = EvaluationDimension.query.get(dim_id)
    if not dim:
        return jsonify({"msg": "维度不存在"}), 404
    if dim.is_actual_assessment:
        return jsonify({"msg": "单位实际考核维度不可删除"}), 400
    plan_id = dim.plan_id
    db.session.delete(dim)
    db.session.flush()
    _sync_actual_assessment_score(plan_id)
    return jsonify({"msg": "删除成功"})


# ==================== 考核维度（单位实际考核下） ====================

@plan_bp.route("/api/dimensions/<int:dim_id>/assessment-dims", methods=["POST"])
@jwt_required()
def add_assessment_dim(dim_id):
    dim = EvaluationDimension.query.get(dim_id)
    if not dim:
        return jsonify({"msg": "评价维度不存在"}), 404

    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"msg": "考核维度名称不能为空"}), 400

    ad = AssessmentDimension(name=name, evaluation_dimension_id=dim_id)
    db.session.add(ad)
    db.session.commit()
    return jsonify({"msg": "添加成功"})


@plan_bp.route("/api/assessment-dims/<int:ad_id>", methods=["PUT"])
@jwt_required()
def update_assessment_dim(ad_id):
    ad = AssessmentDimension.query.get(ad_id)
    if not ad:
        return jsonify({"msg": "考核维度不存在"}), 404
    data = request.get_json()
    if data.get("name"):
        ad.name = data["name"].strip()
    db.session.commit()
    return jsonify({"msg": "编辑成功"})


@plan_bp.route("/api/assessment-dims/<int:ad_id>", methods=["DELETE"])
@jwt_required()
def delete_assessment_dim(ad_id):
    ad = AssessmentDimension.query.get(ad_id)
    if not ad:
        return jsonify({"msg": "考核维度不存在"}), 404
    db.session.delete(ad)
    db.session.commit()
    return jsonify({"msg": "删除成功"})


# ==================== 主考单位 ====================

@plan_bp.route("/api/plans/<int:plan_id>/assessor-units", methods=["PUT"])
@jwt_required()
def set_assessor_units(plan_id):
    plan = Plan.query.get(plan_id)
    if not plan:
        return jsonify({"msg": "方案不存在"}), 404

    data = request.get_json()
    unit_ids = data.get("unit_ids", [])
    units = Unit.query.filter(Unit.id.in_(unit_ids)).all()
    plan.assessor_units = units
    db.session.commit()
    return jsonify({"msg": f"已设置 {len(units)} 个主考单位"})


# ==================== 被考核分组 ====================

@plan_bp.route("/api/plans/<int:plan_id>/groups", methods=["POST"])
@jwt_required()
def create_group(plan_id):
    plan = Plan.query.get(plan_id)
    if not plan:
        return jsonify({"msg": "方案不存在"}), 404

    data = request.get_json()
    name = data.get("name", "").strip()
    unit_ids = data.get("unit_ids", [])
    weights = data.get("dimension_weights", [])  # [{assessment_dimension_id, weight}]

    if not name:
        return jsonify({"msg": "分组名称不能为空"}), 400

    # 校验权重合计
    total_weight = sum(w["weight"] for w in weights)
    if abs(total_weight - 100) > 0.01:
        return jsonify({"msg": f"考核维度权重合计为{total_weight}%，应为100%"}), 400

    group = AssessedGroup(name=name, plan_id=plan_id)
    db.session.add(group)
    db.session.flush()

    if unit_ids:
        group.units = Unit.query.filter(Unit.id.in_(unit_ids)).all()

    for w in weights:
        db.session.add(GroupDimensionWeight(
            group_id=group.id,
            assessment_dimension_id=w["assessment_dimension_id"],
            weight=float(w["weight"]),
        ))

    db.session.commit()
    return jsonify({"msg": "创建成功"})


@plan_bp.route("/api/groups/<int:group_id>", methods=["PUT"])
@jwt_required()
def update_group(group_id):
    group = AssessedGroup.query.get(group_id)
    if not group:
        return jsonify({"msg": "分组不存在"}), 404

    data = request.get_json()
    if data.get("name"):
        group.name = data["name"].strip()

    if data.get("unit_ids") is not None:
        group.units = Unit.query.filter(Unit.id.in_(data["unit_ids"])).all()

    if data.get("dimension_weights") is not None:
        weights = data["dimension_weights"]
        total_weight = sum(w["weight"] for w in weights)
        if abs(total_weight - 100) > 0.01:
            return jsonify({"msg": f"考核维度权重合计为{total_weight}%，应为100%"}), 400

        GroupDimensionWeight.query.filter_by(group_id=group.id).delete()
        for w in weights:
            db.session.add(GroupDimensionWeight(
                group_id=group.id,
                assessment_dimension_id=w["assessment_dimension_id"],
                weight=float(w["weight"]),
            ))

    db.session.commit()
    return jsonify({"msg": "编辑成功"})


@plan_bp.route("/api/groups/<int:group_id>", methods=["DELETE"])
@jwt_required()
def delete_group(group_id):
    group = AssessedGroup.query.get(group_id)
    if not group:
        return jsonify({"msg": "分组不存在"}), 404
    db.session.delete(group)
    db.session.commit()
    return jsonify({"msg": "删除成功"})


# ==================== 单位列表（供方案选择） ====================

@plan_bp.route("/api/units-tree", methods=["GET"])
@jwt_required()
def units_tree():
    orgs = Organization.query.order_by(Organization.sort_order, Organization.id).all()
    all_units = Unit.query.order_by(Unit.id).all()

    unit_by_org = {}
    for u in all_units:
        unit_by_org.setdefault(u.org_id, []).append({"id": u.id, "name": u.name})

    def build(parent_id=None):
        nodes = []
        for o in orgs:
            if o.parent_id == parent_id:
                children = build(o.id)
                units = unit_by_org.get(o.id, [])
                if children or units:
                    nodes.append({
                        "id": "org_" + str(o.id),
                        "name": o.name,
                        "type": "org",
                        "children": children + [{"id": u["id"], "name": u["name"], "type": "unit"} for u in units],
                    })
                else:
                    nodes.append({
                        "id": "org_" + str(o.id),
                        "name": o.name,
                        "type": "org",
                    })
        return nodes

    return jsonify({"data": build(None)})
