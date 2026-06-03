"""权限控制装饰器"""
from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt_identity
from models import db, User, Role, RolePermission


def require_perm(perm_code):
    """检查当前用户是否拥有指定权限，否则返回 403"""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user_id = get_jwt_identity()
            if not user_id:
                return jsonify({"msg": "未登录"}), 401
            user = db.session.get(User, int(user_id))
            if not user:
                return jsonify({"msg": "用户不存在"}), 403

            if not user.role_id:
                return jsonify({"msg": "无权限"}), 403

            role = db.session.get(Role, user.role_id)
            if not role:
                return jsonify({"msg": "无权限"}), 403

            # 系统管理员拥有所有权限
            if role.is_system:
                return fn(*args, **kwargs)

            # 检查角色的菜单权限
            perms = RolePermission.query.filter_by(role_id=role.id).all()
            perm_codes = {p.menu_code for p in perms if p.can_access}

            if perm_code in perm_codes:
                return fn(*args, **kwargs)

            return jsonify({"msg": "无权限"}), 403
        return wrapper
    return decorator
