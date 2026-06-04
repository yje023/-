"""任务查询构建器 - 所有任务筛选逻辑集中管理"""

from models import db, Task, AssessmentDimension, Unit


def build_task_query(
    plan_id=None,
    status=None,
    search=None,
    search_type="all",
    assessor_unit_id=None,
    unit_id=None,
    dimension_ids=None,
    key_works=None,
    period=None,
    user=None,
):
    """
    构建任务查询，统一 list_tasks 和所有 export 端点的筛选逻辑。

    参数：
        plan_id: 方案 ID
        status: 任务状态
        search: 全文搜索关键词
        search_type: 搜索范围 (all / key_work / main_task / dimension / assessor / unit)
        assessor_unit_id: 评价部门 ID（逗号分隔多个）
        unit_id: 被考核单位 ID（逗号分隔多个）
        dimension_ids: 考核维度 ID（逗号分隔多个）
        key_works: 重点工作（逗号分隔多个）
        period: 晾晒周期（逗号分隔多个，如 "monthly,quarterly"）
        user: 当前用户（用于权限过滤）

    返回：
        SQLAlchemy Query 对象
    """
    q = Task.query

    if plan_id:
        q = q.filter(Task.plan_id == plan_id)
    if status:
        statuses = [s.strip() for s in str(status).split(",") if s.strip()]
        if len(statuses) == 1:
            q = q.filter(Task.status == statuses[0])
        elif len(statuses) > 1:
            q = q.filter(Task.status.in_(statuses))
    if period:
        periods = [p.strip() for p in str(period).split(",") if p.strip()]
        if periods:
            q = q.filter(Task.review_period.in_(periods))
    if assessor_unit_id:
        ids = [int(x) for x in str(assessor_unit_id).split(",") if x.strip().isdigit()]
        if ids:
            q = q.filter(Task.assessor_unit_id.in_(ids))
    if unit_id:
        ids = [int(x) for x in str(unit_id).split(",") if x.strip().isdigit()]
        if ids:
            q = q.filter(Task.unit_id.in_(ids))
    if dimension_ids:
        ids = [int(x) for x in str(dimension_ids).split(",") if x.strip().isdigit()]
        if ids:
            q = q.filter(Task.assessment_dimension_id.in_(ids))
    if key_works:
        kws = [x.strip() for x in str(key_works).split(",") if x.strip()]
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
        else:  # all — 搜索全部字段（子查询避免 join 干扰）
            q = q.filter(
                db.or_(
                    Task.key_work.contains(search),
                    Task.main_task.contains(search),
                    Task.scoring_note.contains(search),
                    Task.review_period.contains(search),
                    Task.assessment_dimension_id.in_(
                        db.session.query(AssessmentDimension.id).filter(AssessmentDimension.name.contains(search))
                    ),
                    Task.unit_id.in_(
                        db.session.query(Unit.id).filter(Unit.name.contains(search))
                    ),
                    Task.assessor_unit_id.in_(
                        db.session.query(Unit.id).filter(Unit.name.contains(search))
                    ),
                )
            )

    # 权限过滤
    if user:
        is_publisher = user.role and user.role.is_system
        if not is_publisher:
            if user.current_identity == "assessed":
                q = q.filter(Task.unit_id == user.unit_id)
                # 被考核单位看不到 draft 状态的任务
                q = q.filter(Task.status != "draft")
            elif user.current_identity == "assessor":
                q = q.filter(Task.assessor_unit_id == user.unit_id)

    return q
