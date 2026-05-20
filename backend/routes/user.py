from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from models import db, User, Unit

user_bp = Blueprint("user", __name__)


@user_bp.route("/api/users", methods=["GET"])
@jwt_required()
def list_users():
    search = request.args.get("search", "").strip()
    unit_id = request.args.get("unit_id", type=int)
    role_id = request.args.get("role_id", type=int)
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    page_size = min(page_size, 200)

    q = User.query
    if search:
        q = q.filter(User.username.contains(search))
    if unit_id:
        q = q.filter(User.unit_id == unit_id)
    if role_id:
        q = q.filter(User.role_id == role_id)

    total = q.count()
    users = q.order_by(User.id).offset((page - 1) * page_size).limit(page_size).all()
    items = [{
        "id": u.id,
        "username": u.username,
        "password": u.password_text or "",
        "unit_id": u.unit_id,
        "unit_name": u.unit.name if u.unit else "",
        "role_id": u.role_id,
        "role_name": u.role.name if u.role else "",
        "current_identity": u.current_identity,
        "must_change_password": u.must_change_password,
        "created_at": str(u.created_at),
    } for u in users]
    return jsonify({"data": {"items": items, "total": total, "page": page, "page_size": page_size}})


@user_bp.route("/api/users", methods=["POST"])
@jwt_required()
def create_user():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    unit_id = data.get("unit_id")
    role_id = data.get("role_id")

    if not username:
        return jsonify({"msg": "用户名不能为空"}), 400
    if not password:
        return jsonify({"msg": "密码不能为空"}), 400
    if len(password) < 6:
        return jsonify({"msg": "密码至少6位"}), 400
    if not unit_id:
        return jsonify({"msg": "请选择所属单位"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"msg": "用户名已存在"}), 400

    user = User(username=username, unit_id=unit_id, role_id=role_id or None, current_identity="assessed", password_text=password)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify({"msg": "创建成功"})


@user_bp.route("/api/users/<int:user_id>", methods=["PUT"])
@jwt_required()
def update_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "用户不存在"}), 404

    data = request.get_json()
    username = data.get("username", "").strip()

    if not username:
        return jsonify({"msg": "用户名不能为空"}), 400

    existing = User.query.filter(User.username == username, User.id != user_id).first()
    if existing:
        return jsonify({"msg": "用户名已存在"}), 400

    user.username = username
    if data.get("password"):
        pwd = data["password"].strip()
        if len(pwd) < 6:
            return jsonify({"msg": "密码至少6位"}), 400
        user.set_password(pwd)
        user.password_text = pwd
        user.must_change_password = True
    if data.get("role_id") is not None:
        user.role_id = data["role_id"] or None

    db.session.commit()
    return jsonify({"msg": "编辑成功"})


@user_bp.route("/api/users/<int:user_id>", methods=["DELETE"])
@jwt_required()
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "用户不存在"}), 404

    db.session.delete(user)
    db.session.commit()
    return jsonify({"msg": "删除成功"})


@user_bp.route("/api/users/batch-delete", methods=["POST"])
@jwt_required()
def batch_delete_users():
    data = request.get_json()
    ids = data.get("ids", [])
    if not ids:
        return jsonify({"msg": "请选择要删除的用户"}), 400

    User.query.filter(User.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"msg": f"已删除 {len(ids)} 个用户"})
