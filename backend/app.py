import os
import sys
import logging
from flask import Flask, send_from_directory, request, jsonify
from flask_compress import Compress
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token
from config import Config
from models import db

# 日志配置
import logging.handlers

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

if os.environ.get("ASSESSMENT_ENV") == "production":
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "assessment.log"),
        maxBytes=10 * 1024 * 1024, backupCount=10, encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.getLogger().addHandler(file_handler)
    logger.info("Production file logging initialized")

app = Flask(__name__, static_folder=None)
app.config.from_object(Config)

CORS(app, resources={r"/api/*": {"origins": "*"}})
Compress(app)
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
    """桌面版自动认证：无 token 时注入管理员身份（生产环境禁用）"""
    if os.environ.get("ASSESSMENT_ENV") == "production":
        return
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


# ========== 错误处理中间件 ==========

@app.errorhandler(400)
def bad_request(error):
    return jsonify({"msg": str(error.description) if hasattr(error, 'description') else "请求参数错误", "code": 400}), 400

@app.errorhandler(401)
def unauthorized(error):
    return jsonify({"msg": "未授权，请重新登录", "code": 401}), 401

@app.errorhandler(403)
def forbidden(error):
    return jsonify({"msg": "权限不足", "code": 403}), 403

@app.errorhandler(404)
def not_found(error):
    return jsonify({"msg": "资源不存在", "code": 404}), 404

@app.errorhandler(500)
def server_error(error):
    logger.error(f"500 error: {error}", exc_info=True)
    return jsonify({"msg": "服务器内部错误", "code": 500}), 500

# ========== 请求日志 + 安全响应头 ==========

@app.before_request
def log_request():
    if request.path.startswith("/api/"):
        logger.info(f"{request.method} {request.path}")

@app.after_request
def add_cache_headers(response):
    # 静态资源（带内容哈希）可长期缓存
    if request.path.startswith("/assets/"):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

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
from routes.quality_check import qc_bp
from routes.user_prefs import user_prefs_bp
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
app.register_blueprint(qc_bp)
app.register_blueprint(user_prefs_bp)


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


def _drop_old_checklist_tables():
    """删除旧版清单管理表（checklist + checklist_unit），迁移至 checklist_item"""
    import sqlite3
    conn = sqlite3.connect(app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", ""))
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "checklist" in tables or "checklist_unit" in tables:
            old_count = conn.execute("SELECT COUNT(*) FROM checklist").fetchone()[0] if "checklist" in tables else 0
            if old_count > 0:
                print(f"[数据迁移] 检测到 {old_count} 条旧版清单数据，旧表将删除。建议先通过旧版接口导出数据。")
            conn.execute("DROP TABLE IF EXISTS checklist_unit")
            conn.execute("DROP TABLE IF EXISTS checklist")
            conn.commit()
            print("[数据迁移] 旧版清单表已删除")
    except Exception as e:
        print(f"[数据迁移] 删除旧表时出错: {e}")
    finally:
        conn.close()


def _migrate_proxy_metrics():
    """将 ConfirmedPattern 中的代理指标确认记录迁移到 ProxyMetricPair 表"""
    import sqlite3
    conn = sqlite3.connect(app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", ""))
    try:
        # 确保 proxy_metric_pair 表存在
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "proxy_metric_pair" not in tables:
            return  # 表会在 db.create_all() 中创建
        if "confirmed_pattern" not in tables:
            return

        # 查询旧确认记录
        old_rows = conn.execute(
            "SELECT id, plan_id, text_hash FROM confirmed_pattern WHERE issue_type = '疑似以指标考指标'"
        ).fetchall()
        if not old_rows:
            return

        migrated = 0
        for row in old_rows:
            cp_id, plan_id, text_hash = row
            parts = text_hash.split(":")
            if len(parts) != 2:
                continue
            try:
                tid_a, tid_b = int(parts[0]), int(parts[1])
            except ValueError:
                continue

            # 确保 task_id_a < task_id_b（规范化存储）
            if tid_a > tid_b:
                tid_a, tid_b = tid_b, tid_a

            # 检查 pair 是否已存在
            existing = conn.execute(
                "SELECT id FROM proxy_metric_pair WHERE plan_id = ? AND task_id_a = ? AND task_id_b = ?",
                (plan_id, tid_a, tid_b),
            ).fetchone()
            if existing:
                continue

            # 查找 middle_unit_id：task_id_a 的被考核单位（即中间单位）
            task_info = conn.execute(
                "SELECT unit_id FROM task WHERE id = ?", (tid_a,)
            ).fetchone()
            middle_unit_id = task_info[0] if task_info else None

            conn.execute(
                """INSERT INTO proxy_metric_pair
                   (plan_id, task_id_a, task_id_b, middle_unit_id, similarity, confidence, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 0.0, 'medium', 'confirmed', datetime('now'), datetime('now'))""",
                (plan_id, tid_a, tid_b, middle_unit_id),
            )
            migrated += 1

        if migrated > 0:
            conn.execute(
                "DELETE FROM confirmed_pattern WHERE issue_type = '疑似以指标考指标'"
            )
            conn.commit()
            print(f"[数据迁移] 已迁移 {migrated} 条代理指标确认记录到 proxy_metric_pair 表")
    except Exception as e:
        print(f"[数据迁移] 代理指标迁移出错: {e}")
    finally:
        conn.close()


def _backfill_org_category():
    """为已有组织自动推断类别：乡镇街道根节点及其子孙 → street，其余 → dept"""
    from models import Organization
    import sqlite3
    conn = sqlite3.connect(app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", ""))
    try:
        uncategorized = conn.execute(
            "SELECT COUNT(*) FROM organization WHERE category IS NULL OR category = ''"
        ).fetchone()[0]
        if uncategorized == 0:
            return
        # 找到"乡镇街道"根节点
        street_root = conn.execute(
            "SELECT id FROM organization WHERE name = '乡镇街道' AND (category IS NULL OR category = '') LIMIT 1"
        ).fetchone()
        if street_root:
            # 递归收集所有子孙
            descendants = set()
            stack = [street_root[0]]
            while stack:
                pid = stack.pop()
                children = conn.execute(
                    "SELECT id FROM organization WHERE parent_id = ?", (pid,)
                ).fetchall()
                for c in children:
                    cid = c[0]
                    if cid not in descendants:
                        descendants.add(cid)
                        stack.append(cid)
            all_street_ids = [street_root[0]] + list(descendants)
            placeholders = ",".join("?" for _ in all_street_ids)
            conn.execute(
                f"UPDATE organization SET category = 'street' WHERE id IN ({placeholders})",
                all_street_ids,
            )
            conn.execute(
                "UPDATE organization SET category = 'dept' WHERE (category IS NULL OR category = '')"
            )
        else:
            # 没有"乡镇街道"根节点，根据名称推断
            conn.execute(
                "UPDATE organization SET category = 'street' WHERE name LIKE '%镇%' OR name LIKE '%乡%' OR name LIKE '%街道%'"
            )
            conn.execute(
                "UPDATE organization SET category = 'dept' WHERE (category IS NULL OR category = '')"
            )
        conn.commit()
        done = conn.execute(
            "SELECT COUNT(*) FROM organization WHERE category IS NULL OR category = ''"
        ).fetchone()[0]
        if done == 0:
            print("[回填完成] organization.category 已全部设置")
        else:
            print(f"[回填警告] 仍有 {done} 条机构未设置category")
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


def _create_indexes():
    """为常用查询列创建索引"""
    import sqlite3
    conn = sqlite3.connect(app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", ""))
    try:
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_task_plan_id ON task(plan_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_unit_id ON task(unit_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_assessor_unit_id ON task(assessor_unit_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_assessment_dimension_id ON task(assessment_dimension_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_status ON task(status)",
            "CREATE INDEX IF NOT EXISTS idx_task_review_period ON task(review_period)",
            "CREATE INDEX IF NOT EXISTS idx_task_plan_status ON task(plan_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_task_plan_unit ON task(plan_id, unit_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_unit_id ON user(unit_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_role_id ON user(role_id)",
            "CREATE INDEX IF NOT EXISTS idx_quality_issue_plan_id ON quality_issue(plan_id)",
            "CREATE INDEX IF NOT EXISTS idx_quality_issue_task_id ON quality_issue(task_id)",
            "CREATE INDEX IF NOT EXISTS idx_quality_issue_status ON quality_issue(status)",
            "CREATE INDEX IF NOT EXISTS idx_cadre_unit_id ON cadre(unit_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_submission_task_id ON task_submission(task_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_score_task_id ON task_score(task_id)",
            "CREATE INDEX IF NOT EXISTS idx_assessment_result_cadre_id ON assessment_result(cadre_id)",
            "CREATE INDEX IF NOT EXISTS idx_assessment_result_plan_year ON assessment_result(plan_year)",
            "CREATE INDEX IF NOT EXISTS idx_proxy_metric_pair_plan_id ON proxy_metric_pair(plan_id)",
            "CREATE INDEX IF NOT EXISTS idx_proxy_metric_pair_status ON proxy_metric_pair(status)",
            "CREATE INDEX IF NOT EXISTS idx_proxy_metric_pair_middle_unit ON proxy_metric_pair(middle_unit_id)",
        ]
        for sql in indexes:
            conn.execute(sql)
        conn.commit()
        print("DB migration: indexes created/verified")
    finally:
        conn.close()


def init_db():
    """初始化数据库"""
    with app.app_context():
        db.create_all()
        _migrate_add_column("evaluation_dimension", "is_bonus_deduction", "BOOLEAN", "0")
        _migrate_add_column("organization", "category", "VARCHAR(20)", "''")
        _drop_old_checklist_tables()
        _migrate_nullable_columns()
        _create_indexes()
        _migrate_proxy_metrics()
        _backfill_bonus_deduction()
        _backfill_org_category()
        _clean_task_orphans()
        _seed_default_admin()


if __name__ == "__main__":
    import threading
    import webbrowser

    init_db()

    is_frozen = getattr(sys, 'frozen', False)
    is_production = os.environ.get("ASSESSMENT_ENV") == "production"
    port = int(os.environ.get("PORT", "8080" if is_production else "5000"))

    # 生产环境启用 SQLite WAL 模式，提升并发性能
    if is_production:
        import sqlite3
        db_path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.close()
        logger.info("SQLite WAL mode enabled")

    print("=" * 50)
    print("黔江区多维度精准考核评价系统")
    print(f"环境: {'生产' if is_production else '开发'}")
    print(f"访问地址: http://localhost:{port}")
    print("=" * 50)

    if is_frozen:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    if is_production:
        from waitress import serve
        logger.info(f"Production server (waitress) starting on 0.0.0.0:{port}")
        print(f"生产服务器启动中 (waitress, 端口 {port})...")
        serve(app, host="0.0.0.0", port=port, threads=4, channel_timeout=120)
    else:
        app.run(host="0.0.0.0", port=port, debug=True)
