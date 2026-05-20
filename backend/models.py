from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()


# ==================== 系统后台管理 ====================

# 组织机构-角色关联表（角色可见的组织机构范围）
role_org = db.Table(
    "role_org",
    db.Column("role_id", db.Integer, db.ForeignKey("role.id"), primary_key=True),
    db.Column("org_id", db.Integer, db.ForeignKey("organization.id"), primary_key=True),
)


class Organization(db.Model):
    __tablename__ = "organization"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), nullable=False, comment="机构名称")
    parent_id = db.Column(db.Integer, db.ForeignKey("organization.id"), nullable=True, comment="上级机构ID")
    sort_order = db.Column(db.Integer, default=0, comment="排序")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    parent = db.relationship("Organization", remote_side=[id], backref="children")
    units = db.relationship("Unit", back_populates="organization")


class Unit(db.Model):
    __tablename__ = "unit"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), nullable=False, comment="单位名称")
    org_id = db.Column(db.Integer, db.ForeignKey("organization.id"), nullable=True, comment="所属机构ID")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship("Organization", back_populates="units")
    users = db.relationship("User", back_populates="unit", cascade="all, delete-orphan")


class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(100), unique=True, nullable=False, comment="用户名")
    password_hash = db.Column(db.String(255), nullable=False, comment="密码哈希")
    password_text = db.Column(db.String(100), nullable=True, comment="密码明文")
    unit_id = db.Column(db.Integer, db.ForeignKey("unit.id"), nullable=False, comment="所属单位ID")
    role_id = db.Column(db.Integer, db.ForeignKey("role.id"), nullable=True, comment="角色ID")
    current_identity = db.Column(db.String(20), default="assessed", comment="当前身份: assessor/assessed")
    must_change_password = db.Column(db.Boolean, default=True, comment="是否需要修改初始密码")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    unit = db.relationship("Unit", back_populates="users")
    role = db.relationship("Role", backref="users")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        self.password_text = password

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Role(db.Model):
    __tablename__ = "role"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), unique=True, nullable=False, comment="角色名称")
    is_system = db.Column(db.Boolean, default=False, comment="是否系统预置")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    permissions = db.relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")


class RolePermission(db.Model):
    __tablename__ = "role_permission"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    role_id = db.Column(db.Integer, db.ForeignKey("role.id"), nullable=False)
    menu_code = db.Column(db.String(100), nullable=False, comment="菜单编码")
    can_access = db.Column(db.Boolean, default=True, comment="是否有权限")

    role = db.relationship("Role", back_populates="permissions")


# ==================== 生产端数据管理 ====================

plan_unit = db.Table(
    "plan_unit",
    db.Column("plan_id", db.Integer, db.ForeignKey("plan.id"), primary_key=True),
    db.Column("unit_id", db.Integer, db.ForeignKey("unit.id"), primary_key=True),
)

group_unit = db.Table(
    "group_unit",
    db.Column("group_id", db.Integer, db.ForeignKey("assessed_group.id"), primary_key=True),
    db.Column("unit_id", db.Integer, db.ForeignKey("unit.id"), primary_key=True),
)


class Plan(db.Model):
    __tablename__ = "plan"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), nullable=False, comment="方案名称")
    year = db.Column(db.Integer, nullable=False, comment="考核年度")
    start_date = db.Column(db.Date, nullable=False, comment="方案开始日期")
    end_date = db.Column(db.Date, nullable=False, comment="方案结束日期")
    created_date = db.Column(db.Date, default=datetime.utcnow, comment="创建日期")
    status = db.Column(db.String(20), default="draft", comment="状态: draft/issued/closed")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    assessor_units = db.relationship("Unit", secondary=plan_unit, backref="assessor_plans")
    evaluation_dimensions = db.relationship("EvaluationDimension", back_populates="plan", cascade="all, delete-orphan")
    assessed_groups = db.relationship("AssessedGroup", back_populates="plan", cascade="all, delete-orphan")
    tasks = db.relationship("Task", back_populates="plan", cascade="all, delete-orphan")


class EvaluationDimension(db.Model):
    __tablename__ = "evaluation_dimension"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("plan.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False, comment="维度名称")
    score = db.Column(db.Float, nullable=False, comment="分值")
    is_actual_assessment = db.Column(db.Boolean, default=False, comment="是否单位实际考核维度")
    is_bonus_deduction = db.Column(db.Boolean, default=False, comment="是否加扣分事项维度")
    sort_order = db.Column(db.Integer, default=0)

    plan = db.relationship("Plan", back_populates="evaluation_dimensions")
    assessment_dimensions = db.relationship("AssessmentDimension", back_populates="evaluation_dimension", cascade="all, delete-orphan")


class AssessmentDimension(db.Model):
    __tablename__ = "assessment_dimension"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    evaluation_dimension_id = db.Column(db.Integer, db.ForeignKey("evaluation_dimension.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False, comment="考核维度名称")
    sort_order = db.Column(db.Integer, default=0)

    evaluation_dimension = db.relationship("EvaluationDimension", back_populates="assessment_dimensions")
    group_weights = db.relationship("GroupDimensionWeight", back_populates="assessment_dimension", cascade="all, delete-orphan")


class AssessedGroup(db.Model):
    __tablename__ = "assessed_group"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("plan.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False, comment="分组名称")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    plan = db.relationship("Plan", back_populates="assessed_groups")
    units = db.relationship("Unit", secondary=group_unit, backref="assessed_groups")
    dimension_weights = db.relationship("GroupDimensionWeight", back_populates="group", cascade="all, delete-orphan")


class GroupDimensionWeight(db.Model):
    __tablename__ = "group_dimension_weight"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    group_id = db.Column(db.Integer, db.ForeignKey("assessed_group.id"), nullable=False)
    assessment_dimension_id = db.Column(db.Integer, db.ForeignKey("assessment_dimension.id"), nullable=False)
    weight = db.Column(db.Float, nullable=False, comment="权重百分比")

    group = db.relationship("AssessedGroup", back_populates="dimension_weights")
    assessment_dimension = db.relationship("AssessmentDimension", back_populates="group_weights")


class Task(db.Model):
    __tablename__ = "task"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("plan.id"), nullable=False)
    assessment_dimension_id = db.Column(db.Integer, db.ForeignKey("assessment_dimension.id"), nullable=True)
    unit_id = db.Column(db.Integer, db.ForeignKey("unit.id"), nullable=True, comment="分拨到的被考核单位")
    assessor_unit_id = db.Column(db.Integer, db.ForeignKey("unit.id"), nullable=True, comment="评价部门(主考单位)")
    key_work = db.Column(db.String(300), nullable=False, comment="重点工作名称")
    main_task = db.Column(db.String(300), nullable=False, comment="主要任务名称")
    scoring_note = db.Column(db.Text, comment="评分说明")
    review_period = db.Column(db.String(50), nullable=False, comment="晾晒周期: monthly/quarterly/semiannual/annual")
    status = db.Column(db.String(20), default="pending", comment="状态: pending/submitted/reviewed")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    plan = db.relationship("Plan", back_populates="tasks")
    assessment_dimension = db.relationship("AssessmentDimension", backref="tasks")
    unit = db.relationship("Unit", foreign_keys=[unit_id], backref="received_tasks")
    assessor_unit = db.relationship("Unit", foreign_keys=[assessor_unit_id], backref="assigned_tasks")
    submissions = db.relationship("TaskSubmission", back_populates="task", cascade="all, delete-orphan")
    scores = db.relationship("TaskScore", back_populates="task", cascade="all, delete-orphan")


class TaskSubmission(db.Model):
    __tablename__ = "task_submission"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=False)
    content = db.Column(db.Text, comment="填报内容")
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

    task = db.relationship("Task", back_populates="submissions")


class TaskScore(db.Model):
    __tablename__ = "task_score"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=False)
    score = db.Column(db.Float, comment="打分")
    comment = db.Column(db.Text, comment="评语")
    scored_at = db.Column(db.DateTime, default=datetime.utcnow)

    task = db.relationship("Task", back_populates="scores")
