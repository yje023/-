import os
import sys
from flask import Flask, send_from_directory, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token
from config import Config
from models import db

app = Flask(__name__, static_folder=None)
app.config.from_object(Config)

CORS(app, resources={r"/api/*": {"origins": "*"}})
jwt = JWTManager(app)
db.init_app(app)


def _get_admin_user_id():
    """获取管理员用户 ID，若不存在则返回 None"""
    from models import User
    user = User.query.filter_by(must_change_password=False).first()
    if user:
        return str(user.id)
    user = User.query.first()
    return str(user.id) if user else None


@app.before_request
def desktop_auto_auth():
    """桌面版自动认证：无 token 时注入管理员身份"""
    if not request.path.startswith("/api/"):
        return
    if request.path == "/api/auth/login":
        return
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        user_id = _get_admin_user_id()
        if user_id:
            token = create_access_token(identity=user_id)
            request.environ["HTTP_AUTHORIZATION"] = f"Bearer {token}"


from routes.auth import auth_bp
from routes.org import org_bp
from routes.unit import unit_bp
from routes.user import user_bp
from routes.role import role_bp
from routes.plan import plan_bp
from routes.task import task_bp
from routes.dashboard import dashboard_bp
from routes.checklist import checklist_bp
from routes.cadre import cadre_bp
from routes.assessment_result import result_bp
app.register_blueprint(auth_bp)
app.register_blueprint(org_bp)
app.register_blueprint(unit_bp)
app.register_blueprint(user_bp)
app.register_blueprint(role_bp)
app.register_blueprint(plan_bp)
app.register_blueprint(task_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(checklist_bp)
app.register_blueprint(cadre_bp)
app.register_blueprint(result_bp)


def _get_frontend_dir():
    """获取前端静态文件目录"""
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, 'frontend')
    else:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'dist')


_frontend_dir = _get_frontend_dir()


@app.route("/api/health")
def health():
    return {"status": "ok", "message": "黔江区多维度精准考核评价系统运行中"}


@app.route("/api/version")
def get_version():
    """返回当前版本信息和版本历史"""
    import json
    if getattr(sys, 'frozen', False):
        version_file = os.path.join(sys._MEIPASS, "version.json")
    else:
        version_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.json")
    try:
        with open(version_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"current": data["current"], "history": data["history"]}
    except Exception:
        return {"current": "开发版", "history": []}


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    """服务前端静态文件，SPA 路由回退到 index.html"""
    if path and os.path.exists(os.path.join(_frontend_dir, path)):
        return send_from_directory(_frontend_dir, path)
    # 所有非 API 路径回退到 index.html（SPA 路由）
    if not path.startswith("api/"):
        index_path = os.path.join(_frontend_dir, "index.html")
        if os.path.exists(index_path):
            return send_from_directory(_frontend_dir, "index.html")
    return {"msg": "前端文件未找到，请先构建前端: cd frontend && npm run build"}, 404


def _migrate_add_column(table, col_name, col_type, default_val):
    """SQLite 安全添加列（如已存在则跳过）"""
    import sqlite3
    conn = sqlite3.connect(app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", ""))
    try:
        cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
        if col_name not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type} DEFAULT {default_val}")
            conn.commit()
            print(f"DB migration: added {table}.{col_name}")
    finally:
        conn.close()


def _migrate_nullable_columns():
    """将 admin 表 FK 列改为可空，解除系统管理与生产数据的强耦合"""
    import sqlite3
    conn = sqlite3.connect(app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", ""))
    try:
        info = {row[1]: row for row in conn.execute("PRAGMA table_info(unit)")}
        if not info["org_id"][3]:  # already nullable
            return

        conn.execute("PRAGMA foreign_keys = OFF")

        # 重建 unit 表：org_id 可空
        conn.executescript("""
            CREATE TABLE unit_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) NOT NULL,
                org_id INTEGER,
                created_at DATETIME,
                FOREIGN KEY(org_id) REFERENCES organization(id)
            );
            INSERT INTO unit_new SELECT id, name, org_id, created_at FROM unit;
            DROP TABLE unit;
            ALTER TABLE unit_new RENAME TO unit;
        """)

        # 重建 task 表：unit_id, assessor_unit_id, assessment_dimension_id 可空
        conn.executescript("""
            CREATE TABLE task_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                assessment_dimension_id INTEGER,
                unit_id INTEGER,
                assessor_unit_id INTEGER,
                key_work VARCHAR(300) NOT NULL,
                main_task VARCHAR(300) NOT NULL,
                scoring_note TEXT,
                review_period VARCHAR(50) NOT NULL,
                status VARCHAR(20),
                created_at DATETIME,
                FOREIGN KEY(plan_id) REFERENCES plan(id),
                FOREIGN KEY(assessment_dimension_id) REFERENCES assessment_dimension(id),
                FOREIGN KEY(unit_id) REFERENCES unit(id),
                FOREIGN KEY(assessor_unit_id) REFERENCES unit(id)
            );
            INSERT INTO task_new SELECT id, plan_id, assessment_dimension_id, unit_id, assessor_unit_id,
                key_work, main_task, scoring_note, review_period, status, created_at FROM task;
            DROP TABLE task;
            ALTER TABLE task_new RENAME TO task;
        """)

        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()
        print("DB migration: nullable columns applied")
    finally:
        conn.close()


def _backfill_bonus_deduction():
    """为已有方案补充"加扣分事项"维度"""
    from models import Plan, EvaluationDimension
    with app.app_context():
        plans = Plan.query.all()
        for plan in plans:
            existing = EvaluationDimension.query.filter_by(plan_id=plan.id, is_bonus_deduction=True).first()
            if not existing:
                db.session.add(EvaluationDimension(
                    name="加扣分事项", score=0, is_bonus_deduction=True, plan_id=plan.id
                ))
        db.session.commit()


def _clean_task_orphans():
    """清洗任务表中孤立的 FK 引用"""
    with app.app_context():
        import sqlite3
        db_path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        try:
            orphan_dims = conn.execute("""
                SELECT COUNT(*) FROM task
                WHERE assessment_dimension_id IS NOT NULL
                AND assessment_dimension_id NOT IN (SELECT id FROM assessment_dimension)
            """).fetchone()[0]
            if orphan_dims > 0:
                conn.execute("""
                    UPDATE task SET assessment_dimension_id = NULL
                    WHERE assessment_dimension_id IS NOT NULL
                    AND assessment_dimension_id NOT IN (SELECT id FROM assessment_dimension)
                """)
                conn.commit()
                print(f"[数据清洗] 修复 {orphan_dims} 条任务的孤立考核维度引用")
            orphan_units = conn.execute("""
                SELECT COUNT(*) FROM task
                WHERE unit_id IS NOT NULL
                AND unit_id NOT IN (SELECT id FROM unit)
            """).fetchone()[0]
            if orphan_units > 0:
                conn.execute("""
                    UPDATE task SET unit_id = NULL
                    WHERE unit_id IS NOT NULL
                    AND unit_id NOT IN (SELECT id FROM unit)
                """)
                conn.commit()
                print(f"[数据清洗] 修复 {orphan_units} 条任务的孤立被考核单位引用")
            orphan_assessors = conn.execute("""
                SELECT COUNT(*) FROM task
                WHERE assessor_unit_id IS NOT NULL
                AND assessor_unit_id NOT IN (SELECT id FROM unit)
            """).fetchone()[0]
            if orphan_assessors > 0:
                conn.execute("""
                    UPDATE task SET assessor_unit_id = NULL
                    WHERE assessor_unit_id IS NOT NULL
                    AND assessor_unit_id NOT IN (SELECT id FROM unit)
                """)
                conn.commit()
                print(f"[数据清洗] 修复 {orphan_assessors} 条任务的孤立评价部门引用")
            null_assessors = conn.execute("SELECT COUNT(*) FROM task WHERE assessor_unit_id IS NULL").fetchone()[0]
            null_units = conn.execute("SELECT COUNT(*) FROM task WHERE unit_id IS NULL").fetchone()[0]
            null_dims = conn.execute("SELECT COUNT(*) FROM task WHERE assessment_dimension_id IS NULL").fetchone()[0]
            if null_assessors or null_units or null_dims:
                print(f"[数据清洗] 当前仍有: assessor空={null_assessors}, unit空={null_units}, dim空={null_dims} (需重新导入修正)")
        finally:
            conn.close()


def _seed_default_admin():
    """首次运行时创建默认管理员"""
    from models import Organization, Unit, User, Role

    if User.query.first():
        return  # 已有用户，跳过

    org = Organization(name="系统管理", sort_order=0)
    db.session.add(org)
    db.session.flush()

    unit = Unit(name="系统管理员", org_id=org.id)
    db.session.add(unit)
    db.session.flush()

    role = Role(name="系统管理员", is_system=True)
    db.session.add(role)
    db.session.flush()

    user = User(
        username="admin",
        unit_id=unit.id,
        role_id=role.id,
        current_identity="assessed",
        must_change_password=False,
        password_text="admin123",
    )
    user.set_password("admin123")
    db.session.add(user)
    db.session.commit()
    print("已创建默认管理员账号: admin / admin123")


def init_db():
    """初始化数据库"""
    with app.app_context():
        db.create_all()
        _migrate_add_column("evaluation_dimension", "is_bonus_deduction", "BOOLEAN", "0")
        _migrate_nullable_columns()
        _backfill_bonus_deduction()
        _clean_task_orphans()
        _seed_default_admin()


if __name__ == "__main__":
    import threading
    import webbrowser

    init_db()

    is_frozen = getattr(sys, 'frozen', False)
    port = 5000

    print("=" * 50)
    print("黔江区多维度精准考核评价系统 v1.1")
    print(f"访问地址: http://localhost:{port}")
    print("=" * 50)

    if is_frozen:
        # 打包后自动打开浏览器
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    app.run(host="0.0.0.0", port=port, debug=not is_frozen)
