from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from models import db, Role, RolePermission

role_bp = Blueprint("role", __name__)


@role_bp.route("/api/roles/menus", methods=["GET"])
@jwt_required()
def list_menus():
    menus = [
        {"code": "org", "name": "机构管理", "category": "后台管理"},
        {"code": "unit", "name": "单位管理", "category": "后台管理"},
        {"code": "user", "name": "用户管理", "category": "后台管理"},
        {"code": "role", "name": "角色管理", "category": "后台管理"},
        {"code": "plan", "name": "考核方案", "category": "生产端"},
        {"code": "task", "name": "考核任务", "category": "生产端"},
        {"code": "task_submit", "name": "任务填报", "category": "生产端"},
        {"code": "task_score", "name": "任务打分", "category": "生产端"},
    ]
    return jsonify({"data": menus})


@role_bp.route("/api/roles", methods=["GET"])
@jwt_required()
def list_roles():
    search = request.args.get("search", "").strip()
    q = Role.query
    if search:
        q = q.filter(Role.name.contains(search))
    roles = q.order_by(Role.id).all()

    data = []
    for r in roles:
        perms = {p.menu_code: p.can_access for p in r.permissions}
        data.append({
            "id": r.id,
            "name": r.name,
            "is_system": r.is_system,
            "permissions": perms,
            "created_at": str(r.created_at),
        })
    return jsonify({"data": data})


@role_bp.route("/api/roles", methods=["POST"])
@jwt_required()
def create_role():
    data = request.get_json()
    name = data.get("name", "").strip()
    permissions = data.get("permissions", {})  # { menu_code: true/false }

    if not name:
        return jsonify({"msg": "角色名称不能为空"}), 400
    if Role.query.filter_by(name=name).first():
        return jsonify({"msg": "角色名称已存在"}), 400

    role = Role(name=name)
    db.session.add(role)
    db.session.flush()

    for code, can_access in permissions.items():
        db.session.add(RolePermission(role_id=role.id, menu_code=code, can_access=bool(can_access)))

    db.session.commit()
    return jsonify({"msg": "创建成功"})


@role_bp.route("/api/roles/<int:role_id>", methods=["PUT"])
@jwt_required()
def update_role(role_id):
    role = Role.query.get(role_id)
    if not role:
        return jsonify({"msg": "角色不存在"}), 404

    data = request.get_json()
    name = data.get("name", "").strip()
    permissions = data.get("permissions", {})

    if not name:
        return jsonify({"msg": "角色名称不能为空"}), 400

    existing = Role.query.filter(Role.name == name, Role.id != role_id).first()
    if existing:
        return jsonify({"msg": "角色名称已存在"}), 400

    role.name = name

    # 系统预置角色不可修改
    if not role.is_system and permissions:
        RolePermission.query.filter_by(role_id=role.id).delete()
        for code, can_access in permissions.items():
            db.session.add(RolePermission(role_id=role.id, menu_code=code, can_access=bool(can_access)))

    db.session.commit()
    return jsonify({"msg": "编辑成功"})


@role_bp.route("/api/roles/<int:role_id>", methods=["DELETE"])
@jwt_required()
def delete_role(role_id):
    role = Role.query.get(role_id)
    if not role:
        return jsonify({"msg": "角色不存在"}), 404

    if role.is_system:
        return jsonify({"msg": "系统预置角色不可删除"}), 400

    db.session.delete(role)
    db.session.commit()
    return jsonify({"msg": "删除成功"})
