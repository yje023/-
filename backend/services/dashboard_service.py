from models import db, Plan, Task, Unit, AssessmentDimension, TaskSubmission, TaskScore


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


def _task_query(plan_id, user):
    """构建带角色过滤的任务查询"""
    q = Task.query
    if plan_id:
        q = q.filter(Task.plan_id == plan_id)

    is_publisher = user and user.role and user.role.is_system
    if not is_publisher and user:
        if user.current_identity == "assessed":
            q = q.filter(Task.unit_id == user.unit_id)
        elif user.current_identity == "assessor":
            q = q.filter(Task.assessor_unit_id == user.unit_id)
    return q


def _get_stats(plan_id, user):
    """统计卡片：方案数、单位数、任务数、完成率"""
    plan_q = Plan.query
    if plan_id:
        plan_q = plan_q.filter(Plan.id == plan_id)
    total_plans = plan_q.count()

    q = _task_query(plan_id, user)
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
    q = _task_query(plan_id, user)
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
    q = _task_query(plan_id, user)
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
    q = _task_query(plan_id, user)
    rows = q.with_entities(Task.status, db.func.count(Task.id)).group_by(Task.status).all()
    dist = {"pending": 0, "submitted": 0, "reviewed": 0}
    for status, count in rows:
        dist[status] = count
    return dist


def _get_period_distribution(plan_id, user):
    """晾晒周期分布（饼图）"""
    q = _task_query(plan_id, user)
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
