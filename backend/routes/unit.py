from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required
from models import db, Unit, Organization, User
from utils.xlsx_handler import export_xlsx, parse_import

unit_bp = Blueprint("unit", __name__)


@unit_bp.route("/api/units", methods=["GET"])
@jwt_required()
def list_units():
    search = request.args.get("search", "").strip()
    org_id = request.args.get("org_id", type=int)
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    page_size = min(page_size, 200)

    q = Unit.query
    if search:
        q = q.filter(Unit.name.contains(search))
    if org_id:
        q = q.filter(Unit.org_id == org_id)

    total = q.count()
    units = q.order_by(Unit.id).offset((page - 1) * page_size).limit(page_size).all()
    data = [{"id": u.id, "name": u.name, "org_id": u.org_id, "org_name": u.organization.name if u.organization else "", "created_at": str(u.created_at)} for u in units]
    return jsonify({"data": {"items": data, "total": total, "page": page, "page_size": page_size}})


@unit_bp.route("/api/units", methods=["POST"])
@jwt_required()
def create_unit():
    data = request.get_json()
    name = data.get("name", "").strip()
    org_id = data.get("org_id")

    if not name:
        return jsonify({"msg": "单位名称不能为空"}), 400
    if not org_id:
        return jsonify({"msg": "请选择所属机构"}), 400

    org = Organization.query.get(org_id)
    if not org:
        return jsonify({"msg": "所属机构不存在"}), 400

    if Unit.query.filter_by(name=name, org_id=org_id).first():
        return jsonify({"msg": "该机构下已存在同名单位"}), 400

    unit = Unit(name=name, org_id=org_id)
    db.session.add(unit)
    db.session.flush()

    # 自动创建初始用户
    username = name + "账号"
    user = User(username=username, unit_id=unit.id, current_identity="assessed")
    user.set_password("csma123")
    db.session.add(user)

    db.session.commit()
    return jsonify({"data": {"id": unit.id, "name": unit.name, "org_id": unit.org_id}, "msg": "创建成功"})


@unit_bp.route("/api/units/<int:unit_id>", methods=["PUT"])
@jwt_required()
def update_unit(unit_id):
    unit = Unit.query.get(unit_id)
    if not unit:
        return jsonify({"msg": "单位不存在"}), 404

    data = request.get_json()
    name = data.get("name", "").strip()
    org_id = data.get("org_id")

    if not name:
        return jsonify({"msg": "单位名称不能为空"}), 400

    unit.name = name
    if org_id:
        unit.org_id = org_id
    db.session.commit()
    return jsonify({"msg": "编辑成功"})


@unit_bp.route("/api/units/<int:unit_id>", methods=["DELETE"])
@jwt_required()
def delete_unit(unit_id):
    unit = Unit.query.get(unit_id)
    if not unit:
        return jsonify({"msg": "单位不存在"}), 404

    from models import group_unit, plan_unit

    # 清理与考核方案的关联（不删任务，只解除关联关系）
    db.session.execute(group_unit.delete().where(group_unit.c.unit_id == unit_id))
    db.session.execute(plan_unit.delete().where(plan_unit.c.unit_id == unit_id))

    # 删除关联用户
    User.query.filter_by(unit_id=unit_id).delete()

    db.session.delete(unit)
    db.session.commit()
    return jsonify({"msg": f"已删除单位「{unit.name}」"})


@unit_bp.route("/api/units/<int:unit_id>/move", methods=["PUT"])
@jwt_required()
def move_unit(unit_id):
    unit = Unit.query.get(unit_id)
    if not unit:
        return jsonify({"msg": "单位不存在"}), 404

    data = request.get_json()
    target_org_id = data.get("org_id")
    if not target_org_id:
        return jsonify({"msg": "请选择目标机构"}), 400

    org = Organization.query.get(target_org_id)
    if not org:
        return jsonify({"msg": "目标机构不存在"}), 400

    unit.org_id = target_org_id
    db.session.commit()
    return jsonify({"msg": "移动成功"})


@unit_bp.route("/api/units/batch-delete", methods=["POST"])
@jwt_required()
def batch_delete_units():
    data = request.get_json()
    ids = data.get("ids", [])
    if not ids:
        return jsonify({"msg": "请选择要删除的单位"}), 400

    from models import group_unit, plan_unit

    # 清理与考核方案的关联
    db.session.execute(group_unit.delete().where(group_unit.c.unit_id.in_(ids)))
    db.session.execute(plan_unit.delete().where(plan_unit.c.unit_id.in_(ids)))

    # 删除关联用户
    User.query.filter(User.unit_id.in_(ids)).delete(synchronize_session=False)

    # 删除单位
    Unit.query.filter(Unit.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"msg": f"已删除 {len(ids)} 个单位"})


@unit_bp.route("/api/units/import", methods=["POST"])
@jwt_required()
def import_units():
    if "file" not in request.files:
        return jsonify({"msg": "请上传文件"}), 400

    file = request.files["file"]
    if not file.filename.endswith((".xlsx", ".xls")):
        return jsonify({"msg": "仅支持 .xlsx 文件"}), 400

    headers, rows = parse_import(file.stream, ["单位名称", "所属机构名称"])
    if headers is None:
        return jsonify({"msg": rows}), 400

    created = 0
    errors = []
    for i, row in enumerate(rows, 2):
        name = row[0] if len(row) > 0 else ""
        org_name = row[1] if len(row) > 1 else ""

        if not name:
            errors.append(f"第{i}行：单位名称不能为空")
            continue
        if not org_name:
            errors.append(f"第{i}行：所属机构名称不能为空")
            continue

        org = Organization.query.filter_by(name=org_name).first()
        if not org:
            errors.append(f"第{i}行：机构「{org_name}」不存在")
            continue

        if Unit.query.filter_by(name=name, org_id=org.id).first():
            errors.append(f"第{i}行：单位「{name}」在机构「{org_name}」下已存在")
            continue

        unit = Unit(name=name, org_id=org.id)
        db.session.add(unit)
        db.session.flush()

        username = name + "账号"
        user = User(username=username, unit_id=unit.id, current_identity="assessed")
        user.set_password("csma123")
        db.session.add(user)

        created += 1

    db.session.commit()

    result = {"msg": f"成功导入 {created} 个单位"}
    if errors:
        result["errors"] = errors
    return jsonify(result)


@unit_bp.route("/api/units/export", methods=["GET"])
@jwt_required()
def export_units():
    units = Unit.query.order_by(Unit.id).all()
    rows = [[u.name, u.organization.name if u.organization else ""] for u in units]
    output = export_xlsx(["单位名称", "所属机构名称"], rows)
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="单位列表.xlsx")


@unit_bp.route("/api/units/template", methods=["GET"])
@jwt_required()
def download_template():
    output = export_xlsx(["单位名称", "所属机构名称"], [["示例单位", "示例机构"]])
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="单位导入模板.xlsx")
