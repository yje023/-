from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from models import db, User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"msg": "用户名和密码不能为空"}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"msg": "用户名或密码错误"}), 401

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

    if len(new_pwd) < 6:
        return jsonify({"msg": "新密码至少6位"}), 400

    user.set_password(new_pwd)
    user.password_text = new_pwd
    user.must_change_password = False
    db.session.commit()

    return jsonify({"msg": "密码修改成功"})
