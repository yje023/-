"""用户偏好设置 — 芯片排序等"""
import json
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, ChipSortOrder

user_prefs_bp = Blueprint("user_prefs", __name__)


@user_prefs_bp.route("/api/user/chip-sort-order", methods=["GET"])
@jwt_required()
def get_chip_sort_order():
    """获取指定页面的所有维度芯片排序"""
    page = request.args.get("page", "")
    if not page:
        return jsonify({"msg": "page 参数必填"}), 400
    user_id = int(get_jwt_identity())
    rows = ChipSortOrder.query.filter_by(user_id=user_id, page=page).all()
    result = {}
    for r in rows:
        try:
            result[r.dimension_key] = json.loads(r.sort_order)
        except (json.JSONDecodeError, TypeError):
            result[r.dimension_key] = []
    return jsonify({"data": result})


@user_prefs_bp.route("/api/user/chip-sort-order", methods=["PUT"])
@jwt_required()
def save_chip_sort_order():
    """保存单个维度的芯片排序"""
    data = request.get_json()
    page = data.get("page", "")
    dimension_key = data.get("dimension_key", "")
    sort_order = data.get("sort_order", [])

    if not page or not dimension_key:
        return jsonify({"msg": "page 和 dimension_key 必填"}), 400

    user_id = int(get_jwt_identity())
    row = ChipSortOrder.query.filter_by(
        user_id=user_id, page=page, dimension_key=dimension_key
    ).first()

    if row:
        row.sort_order = json.dumps(sort_order, ensure_ascii=False)
    else:
        row = ChipSortOrder(
            user_id=user_id,
            page=page,
            dimension_key=dimension_key,
            sort_order=json.dumps(sort_order, ensure_ascii=False),
        )
        db.session.add(row)

    db.session.commit()
    return jsonify({"msg": "保存成功"})
