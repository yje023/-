from models import db, Plan, Task, Unit, AssessmentDimension, TaskSubmission, TaskScore, Cadre, AssessmentResult, AssessedGroup
from sqlalchemy import func
from services.task_query import build_task_query


def get_dashboard_overview(plan_id=None, user=None):
    """获取驾驶舱概览数据，按角色过滤数据范围"""
    stats = _get_stats(plan_id, user)
    dim_stats = _get_dimension_stats(plan_id, user)
    unit_completion = _get_unit_completion(plan_id, user)
    status_dist = _get_status_distribution(plan_id, user)
    period_dist = _get_period_distribution(plan_id, user)
    recent_activity = _get_recent_activity(plan_id, user, limit=20)
    return {
        "stats": stats,
        "dim_stats": dim_stats,
        "unit_completion": unit_completion,
        "status_dist": status_dist,
        "period_dist": period_dist,
        "recent_activity": recent_activity,
    }


def _get_stats(plan_id, user):
    """统计卡片：方案数、单位数、任务数、完成率"""
    plan_q = Plan.query
    if plan_id:
        plan_q = plan_q.filter(Plan.id == plan_id)
    total_plans = plan_q.count()

    q = build_task_query(plan_id=plan_id, user=user)
    total_tasks = q.count()
    reviewed_tasks = q.filter(Task.status == "reviewed").count()

    unit_ids = q.with_entities(Task.unit_id).distinct().all()
    total_units = len(unit_ids)

    completion_rate = round(reviewed_tasks / total_tasks * 100, 1) if total_tasks > 0 else 0

    return {
        "total_plans": total_plans,
        "total_units": total_units,
        "total_tasks": total_tasks,
        "reviewed_tasks": reviewed_tasks,
        "completion_rate": completion_rate,
    }


def _get_dimension_stats(plan_id, user):
    """各考核维度任务统计（用于柱状图）"""
    q = build_task_query(plan_id=plan_id, user=user)
    rows = (
        q.with_entities(
            AssessmentDimension.name,
            Task.status,
            db.func.count(Task.id),
        )
        .join(AssessmentDimension, Task.assessment_dimension_id == AssessmentDimension.id)
        .group_by(AssessmentDimension.name, Task.status)
        .order_by(AssessmentDimension.name)
        .all()
    )

    dims = {}
    for name, status, count in rows:
        if name not in dims:
            dims[name] = {"name": name, "total": 0, "pending": 0, "submitted": 0, "reviewed": 0}
        dims[name][status] = count
        dims[name]["total"] += count
    return list(dims.values())


def _get_unit_completion(plan_id, user):
    """各单位完成率排名（TOP 15，用于横向柱状图）"""
    q = build_task_query(plan_id=plan_id, user=user)
    rows = (
        q.with_entities(
            Unit.name,
            db.func.count(Task.id).label("total"),
            db.func.sum(db.case((Task.status == "reviewed", 1), else_=0)).label("reviewed"),
        )
        .join(Unit, Task.unit_id == Unit.id)
        .group_by(Unit.name)
        .order_by(db.text("total DESC"))
        .limit(15)
        .all()
    )

    result = []
    for name, total, reviewed in rows:
        rate = round(reviewed / total * 100, 1) if total > 0 else 0
        result.append({"unit_name": name, "total": total, "completed": reviewed or 0, "rate": rate})
    return result


def _get_status_distribution(plan_id, user):
    """任务状态分布（饼图）"""
    q = build_task_query(plan_id=plan_id, user=user)
    rows = q.with_entities(Task.status, db.func.count(Task.id)).group_by(Task.status).all()
    dist = {"pending": 0, "submitted": 0, "reviewed": 0}
    for status, count in rows:
        dist[status] = count
    return dist


def _get_period_distribution(plan_id, user):
    """晾晒周期分布（饼图）"""
    q = build_task_query(plan_id=plan_id, user=user)
    rows = q.with_entities(Task.review_period, db.func.count(Task.id)).group_by(Task.review_period).all()
    dist = {}
    for period, count in rows:
        dist[period] = count
    return dist


def _get_recent_activity(plan_id, user, limit=20):
    """最近考核动态（填报+打分），直接按 plan_id 过滤避免大量 IN 参数"""
    is_publisher = user and user.role and user.role.is_system

    def _apply_role_filter(q):
        if not is_publisher and user:
            if user.current_identity == "assessed":
                return q.filter(Task.unit_id == user.unit_id)
            elif user.current_identity == "assessor":
                return q.filter(Task.assessor_unit_id == user.unit_id)
        return q

    # 最近填报
    submissions = (
        db.session.query(
            TaskSubmission.submitted_at.label("time"),
            Unit.name.label("unit_name"),
            AssessmentDimension.name.label("dim_name"),
            Task.key_work.label("key_work"),
            db.literal("已提交").label("action"),
            db.literal(None).label("score"),
        )
        .join(Task, TaskSubmission.task_id == Task.id)
        .join(Unit, Task.unit_id == Unit.id)
        .join(AssessmentDimension, Task.assessment_dimension_id == AssessmentDimension.id)
    )
    if plan_id:
        submissions = submissions.filter(Task.plan_id == plan_id)
    submissions = _apply_role_filter(submissions)
    submissions = submissions.order_by(TaskSubmission.submitted_at.desc()).limit(limit // 2)

    # 最近打分
    scores = (
        db.session.query(
            TaskScore.scored_at.label("time"),
            Unit.name.label("unit_name"),
            AssessmentDimension.name.label("dim_name"),
            Task.key_work.label("key_work"),
            db.literal("已打分").label("action"),
            TaskScore.score.label("score"),
        )
        .join(Task, TaskScore.task_id == Task.id)
        .join(Unit, Task.unit_id == Unit.id)
        .join(AssessmentDimension, Task.assessment_dimension_id == AssessmentDimension.id)
    )
    if plan_id:
        scores = scores.filter(Task.plan_id == plan_id)
    scores = _apply_role_filter(scores)
    scores = scores.order_by(TaskScore.scored_at.desc()).limit(limit // 2)

    # 分别执行两个查询，Python 层面合并排序取 TOP N
    sub_items = [{
        "time": str(item.time)[:19] if item.time else "",
        "unit_name": item.unit_name,
        "dim_name": item.dim_name,
        "key_work": item.key_work,
        "action": item.action,
        "score": item.score,
    } for item in submissions.all()]

    score_items = [{
        "time": str(item.time)[:19] if item.time else "",
        "unit_name": item.unit_name,
        "dim_name": item.dim_name,
        "key_work": item.key_work,
        "action": item.action,
        "score": item.score,
    } for item in scores.all()]

    all_activity = sub_items + score_items
    all_activity.sort(key=lambda x: x["time"], reverse=True)
    return all_activity[:limit]


# ==================== 驾驶舱 v1.2 新增 ====================


def get_cadre_stats():
    """干部结构统计"""
    total = Cadre.query.count()

    # 性别分布
    gender_rows = db.session.query(Cadre.gender, func.count(Cadre.id)).group_by(Cadre.gender).all()
    gender_dist = {g: c for g, c in gender_rows}

    # 学历分布
    edu_rows = db.session.query(Cadre.education, func.count(Cadre.id)).group_by(Cadre.education).all()
    education_dist = [{"name": e or "未知", "value": c} for e, c in edu_rows if c]

    # 全日制学历
    ft_edu_rows = db.session.query(Cadre.fulltime_education, func.count(Cadre.id)).group_by(Cadre.fulltime_education).all()
    fulltime_education_dist = [{"name": e or "未知", "value": c} for e, c in ft_edu_rows if c]

    # 政治面貌
    pol_rows = db.session.query(Cadre.political_status, func.count(Cadre.id)).group_by(Cadre.political_status).all()
    political_dist = [{"name": p or "未知", "value": c} for p, c in pol_rows]

    # 民族
    eth_rows = db.session.query(Cadre.ethnicity, func.count(Cadre.id)).group_by(Cadre.ethnicity).all()
    ethnicity_dist = [{"name": e or "未知", "value": c} for e, c in eth_rows]

    # 专业分布
    spec_rows = db.session.query(Cadre.specialty, func.count(Cadre.id)).group_by(Cadre.specialty).all()
    specialty_dist = [{"name": s or "未分类", "value": c} for s, c in spec_rows if c]

    # 擅长领域
    all_expertise = db.session.query(Cadre.expertise).filter(Cadre.expertise.isnot(None), Cadre.expertise != "").all()
    expertise_count = {}
    for (exp,) in all_expertise:
        for item in exp.replace("，", ",").split(","):
            item = item.strip()
            if item:
                expertise_count[item] = expertise_count.get(item, 0) + 1
    expertise_dist = [{"name": k, "value": v} for k, v in sorted(expertise_count.items(), key=lambda x: -x[1])[:30]]

    # 年龄段分布
    from datetime import datetime
    age_groups = {"35岁以下": 0, "35-45岁": 0, "45-55岁": 0, "55岁以上": 0}
    now = datetime.utcnow()
    cadres_with_birth = Cadre.query.filter(Cadre.birth_date.isnot(None)).all()
    for c in cadres_with_birth:
        age = now.year - c.birth_date.year
        if age < 35: age_groups["35岁以下"] += 1
        elif age < 45: age_groups["35-45岁"] += 1
        elif age < 55: age_groups["45-55岁"] += 1
        else: age_groups["55岁以上"] += 1

    return {
        "total": total,
        "gender": {"male": gender_dist.get("男", 0), "female": gender_dist.get("女", 0)},
        "education": sorted(education_dist, key=lambda x: -x["value"]),
        "fulltime_education": sorted(fulltime_education_dist, key=lambda x: -x["value"]),
        "political": political_dist,
        "ethnicity": ethnicity_dist,
        "specialty": specialty_dist,
        "expertise": expertise_dist,
        "age_groups": [{"name": k, "value": v} for k, v in age_groups.items()],
    }


def get_task_progress(plan_id=None, user=None):
    """重点任务管理 — 仪表盘数据"""
    q = build_task_query(plan_id=plan_id, user=user)
    total = q.count()
    pending = q.filter(Task.status == "pending").count()
    submitted = q.filter(Task.status == "submitted").count()
    reviewed = q.filter(Task.status == "reviewed").count()

    rate = round(reviewed / total * 100, 1) if total > 0 else 0
    on_track = round(submitted / total * 100, 1) if total > 0 else 0

    # 按维度统计
    dim_rows = (
        q.with_entities(AssessmentDimension.name, func.count(Task.id))
        .join(AssessmentDimension, Task.assessment_dimension_id == AssessmentDimension.id)
        .group_by(AssessmentDimension.name)
        .all()
    )
    dim_stats = [{"name": d, "count": c} for d, c in dim_rows]

    return {
        "total": total,
        "pending": pending,
        "submitted": submitted,
        "reviewed": reviewed,
        "completion_rate": rate,
        "on_track_rate": on_track,
        "status_cards": [
            {"label": "已完成", "value": reviewed, "rate": rate, "color": "green"},
            {"label": "达到时序进度", "value": submitted, "rate": on_track, "color": "cyan"},
            {"label": "正在推进", "value": pending, "rate": round(pending / total * 100, 1) if total > 0 else 0, "color": "orange"},
            {"label": "推进滞后或未开展", "value": 0, "rate": 0, "color": "red"},
        ],
        "dim_stats": dim_stats,
    }


def get_task_flow(plan_id=None, user=None):
    """考核系统进度监控 — 桑基图数据"""
    q = build_task_query(plan_id=plan_id, user=user)

    # 按考核维度统计任务数，作为流转节点
    dim_rows = (
        q.with_entities(AssessmentDimension.name, func.count(Task.id))
        .join(AssessmentDimension, Task.assessment_dimension_id == AssessmentDimension.id)
        .group_by(AssessmentDimension.name)
        .all()
    )

    # 构建简化的流转数据：维度 -> 状态
    nodes = [{"name": "考核办发布"}]
    links = []

    for dim_name, count in dim_rows:
        nodes.append({"name": dim_name})
        links.append({"source": "考核办发布", "target": dim_name, "value": count})

    # 按状态统计
    status_counts = q.with_entities(Task.status, func.count(Task.id)).group_by(Task.status).all()
    status_nodes = []
    for status, count in status_counts:
        status_name = {"pending": "待填报", "submitted": "已提交", "reviewed": "已审核"}.get(status, status)
        status_nodes.append({"name": f"{status_name}({count})"})

    # 状态节点
    for dim_name, _ in dim_rows:
        for status, count in status_counts:
            status_name = {"pending": "待填报", "submitted": "已提交", "reviewed": "已审核"}.get(status, status)
            # 每个维度到状态有一条边（模拟数据）
            links.append({"source": dim_name, "target": f"{status_name}({count})", "value": max(1, count // 3)})

    nodes.extend(status_nodes)

    return {"nodes": nodes, "links": links}


def get_assessment_results(plan_year=None, position_type=None):
    """考核结果数据"""
    q = AssessmentResult.query
    if plan_year:
        q = q.filter(AssessmentResult.plan_year == plan_year)
    if position_type:
        q = q.filter(AssessmentResult.position_type == position_type)

    results = q.order_by(AssessmentResult.rank.asc().nullslast()).all()
    return [{
        "rank": r.rank,
        "cadre_name": r.cadre.name if r.cadre else "",
        "unit_name": r.cadre.unit.name if r.cadre and r.cadre.unit else "",
        "total_score": r.total_score,
        "has_violation": r.has_violation,
        "is_excellent": r.is_excellent,
        "position_type": r.position_type,
    } for r in results]


def get_task_decomposition(plan_id=None, user=None):
    """任务解构管理 — 层级环形图数据"""
    q = build_task_query(plan_id=plan_id, user=user)

    # 按考核维度和状态统计
    rows = (
        q.with_entities(AssessmentDimension.name, Task.status, func.count(Task.id))
        .join(AssessmentDimension, Task.assessment_dimension_id == AssessmentDimension.id)
        .group_by(AssessmentDimension.name, Task.status)
        .all()
    )

    dims = {}
    for name, status, count in rows:
        if name not in dims:
            dims[name] = {"name": name, "total": 0, "pending": 0, "submitted": 0, "reviewed": 0}
        dims[name][status] = count
        dims[name]["total"] += count

    # 构建 sunburst 数据
    sunburst_data = []
    dim_list = list(dims.values())
    for d in dim_list:
        sunburst_data.append({"name": d["name"], "value": d["total"], "children": [
            {"name": "待填报", "value": d["pending"]},
            {"name": "已提交", "value": d["submitted"]},
            {"name": "已审核", "value": d["reviewed"]},
        ]})

    # 精准解构数（已分配到维度的任务）、主动申报数（已提交的）
    precise_count = sum(1 for d in dim_list if d["total"] > 0)
    declared_count = sum(d["submitted"] for d in dim_list)

    return {
        "sunburst": sunburst_data,
        "stats": {
            "precise_count": precise_count,
            "declared_count": declared_count,
            "total_count": sum(d["total"] for d in dim_list),
        },
        "dim_list": [{"name": d["name"], "total": d["total"]} for d in dim_list],
    }
