from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required
from models import db, Checklist, Unit
from utils.xlsx_handler import export_xlsx, parse_import

checklist_bp = Blueprint("checklist", __name__)


def _checklist_to_dict(c):
    return {
        "id": c.id,
        "name": c.name,
        "unit_count": len(c.units),
        "unit_ids": [u.id for u in c.units],
        "unit_names": [u.name for u in c.units],
        "created_at": str(c.created_at) if c.created_at else None,
    }


@checklist_bp.route("/api/checklists", methods=["GET"])
@jwt_required()
def list_checklists():
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    page_size = min(page_size, 200)
    search = request.args.get("search", "")

    q = Checklist.query
    if search:
        q = q.filter(Checklist.name.contains(search))
    total = q.count()
    items = q.order_by(Checklist.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return jsonify({"data": {
        "items": [_checklist_to_dict(c) for c in items],
        "total": total, "page": page, "page_size": page_size,
    }})


@checklist_bp.route("/api/checklists", methods=["POST"])
@jwt_required()
def create_checklist():
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"msg": "清单名称不能为空"}), 400

    c = Checklist(name=data["name"].strip())
    if data.get("unit_ids"):
        units = Unit.query.filter(Unit.id.in_(data["unit_ids"])).all()
        c.units = units
    db.session.add(c)
    db.session.commit()
    return jsonify({"data": _checklist_to_dict(c), "msg": "创建成功"})


@checklist_bp.route("/api/checklists/<int:checklist_id>", methods=["PUT"])
@jwt_required()
def update_checklist(checklist_id):
    c = Checklist.query.get(checklist_id)
    if not c:
        return jsonify({"msg": "清单不存在"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"msg": "无效数据"}), 400
    if "name" in data and data["name"]:
        c.name = data["name"].strip()
    if "unit_ids" in data:
        c.units = Unit.query.filter(Unit.id.in_(data["unit_ids"])).all() if data["unit_ids"] else []
    db.session.commit()
    return jsonify({"data": _checklist_to_dict(c), "msg": "更新成功"})


@checklist_bp.route("/api/checklists/<int:checklist_id>", methods=["DELETE"])
@jwt_required()
def delete_checklist(checklist_id):
    c = Checklist.query.get(checklist_id)
    if not c:
        return jsonify({"msg": "清单不存在"}), 404
    db.session.delete(c)
    db.session.commit()
    return jsonify({"msg": "删除成功"})


@checklist_bp.route("/api/checklists/batch-delete", methods=["POST"])
@jwt_required()
def batch_delete_checklists():
    data = request.get_json()
    if not data or not data.get("ids"):
        return jsonify({"msg": "请选择要删除的清单"}), 400
    Checklist.query.filter(Checklist.id.in_(data["ids"])).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"msg": f"成功删除 {len(data['ids'])} 个清单"})


@checklist_bp.route("/api/checklists/<int:checklist_id>/units", methods=["GET"])
@jwt_required()
def get_checklist_units(checklist_id):
    c = Checklist.query.get(checklist_id)
    if not c:
        return jsonify({"msg": "清单不存在"}), 404
    return jsonify({"data": [_checklist_to_dict(c)]})


@checklist_bp.route("/api/checklists/import", methods=["POST"])
@jwt_required()
def import_checklists():
    if "file" not in request.files:
        return jsonify({"msg": "请上传文件"}), 400
    file = request.files["file"]
    if not file.filename.endswith((".xlsx", ".xls")):
        return jsonify({"msg": "仅支持 .xlsx 文件"}), 400

    headers, rows = parse_import(file.stream, ["清单名称", "单位名称"])
    if headers is None:
        return jsonify({"msg": rows}), 400

    checklist_map = {}
    errors = []
    for i, row in enumerate(rows, start=2):
        name = (row[0] or "").strip()
        unit_name = (row[1] or "").strip() if len(row) > 1 else ""
        if not name:
            continue
        unit = Unit.query.filter_by(name=unit_name).first() if unit_name else None
        if unit_name and not unit:
            errors.append(f"第{i}行：单位「{unit_name}」不存在")
            continue
        if name not in checklist_map:
            c = Checklist(name=name)
            db.session.add(c)
            db.session.flush()
            checklist_map[name] = c
        if unit:
            if unit not in checklist_map[name].units:
                checklist_map[name].units.append(unit)

    if errors:
        db.session.rollback()
        return jsonify({"msg": f"导入失败：{'; '.join(errors[:10])}"}), 400

    db.session.commit()
    return jsonify({"msg": f"成功导入 {len(checklist_map)} 个清单"})


@checklist_bp.route("/api/checklists/export", methods=["GET"])
@jwt_required()
def export_checklists():
    checklists = Checklist.query.order_by(Checklist.id).all()
    rows = []
    for c in checklists:
        if c.units:
            for u in c.units:
                rows.append([c.name, u.name])
        else:
            rows.append([c.name, ""])
    output = export_xlsx(["清单名称", "单位名称"], rows)
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="清单列表.xlsx")


@checklist_bp.route("/api/checklists/template", methods=["GET"])
@jwt_required()
def download_template():
    output = export_xlsx(["清单名称", "单位名称"], [["示例清单", "示例单位"]])
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="清单导入模板.xlsx")
