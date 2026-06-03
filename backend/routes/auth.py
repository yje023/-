import time
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from models import db, User

auth_bp = Blueprint("auth", __name__)

# 简易登录限流：每个IP每分钟最多5次尝试
_login_attempts = {}  # {ip: [timestamps]}


def _check_rate_limit(ip):
    """检查IP登录频率，返回 (是否允许, 剩余等待秒数)"""
    now = time.time()
    window = 60  # 1分钟窗口
    max_attempts = 5
    if ip not in _login_attempts:
        _login_attempts[ip] = []
    # 清理过期记录
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < window]
    if len(_login_attempts[ip]) >= max_attempts:
        wait = int(window - (now - _login_attempts[ip][0]))
        return False, max(wait, 1)
    _login_attempts[ip].append(now)
    return True, 0


@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    # 限流检查
    client_ip = request.remote_addr or "127.0.0.1"
    allowed, wait = _check_rate_limit(client_ip)
    if not allowed:
        return jsonify({"msg": f"登录尝试过于频繁，请 {wait} 秒后重试"}), 429

    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"msg": "用户名和密码不能为空"}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"msg": "用户名或密码错误"}), 401

    # 自动设置默认身份：管理员或主考单位角色 → assessor
    if user.role and (user.role.is_system or user.role.name == "主考单位"):
        user.current_identity = "assessor"
        db.session.commit()

    access_token = create_access_token(identity=str(user.id))
    return jsonify({
        "access_token": access_token,
        "must_change_password": user.must_change_password,
    })


@auth_bp.route("/api/auth/me", methods=["GET"])
@jwt_required()
def get_me():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "用户不存在"}), 404

    return jsonify({
        "id": user.id,
        "username": user.username,
        "unit_id": user.unit_id,
        "unit_name": user.unit.name if user.unit else None,
        "role_id": user.role_id,
        "role_name": user.role.name if user.role else None,
        "current_identity": user.current_identity,
        "must_change_password": user.must_change_password,
    })


@auth_bp.route("/api/auth/identity", methods=["PUT"])
@jwt_required()
def switch_identity():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "用户不存在"}), 404

    new_identity = "assessor" if user.current_identity == "assessed" else "assessed"
    user.current_identity = new_identity
    db.session.commit()

    return jsonify({
        "id": user.id,
        "username": user.username,
        "unit_id": user.unit_id,
        "unit_name": user.unit.name if user.unit else None,
        "role_id": user.role_id,
        "role_name": user.role.name if user.role else None,
        "current_identity": user.current_identity,
        "must_change_password": user.must_change_password,
    })


@auth_bp.route("/api/auth/password", methods=["PUT"])
@jwt_required()
def change_password():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "用户不存在"}), 404

    data = request.get_json()
    old_pwd = data.get("old_password", "")
    new_pwd = data.get("new_password", "")

    if not old_pwd or not new_pwd:
        return jsonify({"msg": "参数不完整"}), 400

    if not user.check_password(old_pwd):
        return jsonify({"msg": "旧密码错误"}), 400

    if not new_pwd:
        return jsonify({"msg": "新密码不能为空"}), 400

    user.set_password(new_pwd)
    user.must_change_password = False
    db.session.commit()

    return jsonify({"msg": "密码修改成功"})
