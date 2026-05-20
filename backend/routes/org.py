from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required
from models import db, Organization
from utils.xlsx_handler import export_xlsx, parse_import
import io

org_bp = Blueprint("org", __name__)


@org_bp.route("/api/orgs", methods=["GET"])
@jwt_required()
def list_orgs():
    search = request.args.get("search", "").strip()
    q = Organization.query
    if search:
        q = q.filter(Organization.name.contains(search))
    orgs = q.order_by(Organization.sort_order, Organization.id).all()

    def build_tree(parent_id=None):
        nodes = []
        for o in orgs:
            if o.parent_id == parent_id:
                nodes.append({
                    "id": o.id,
                    "name": o.name,
                    "parent_id": o.parent_id,
                    "sort_order": o.sort_order,
                    "children": build_tree(o.id),
                })
        return nodes

    tree = build_tree(None)
    return jsonify({"data": tree})


@org_bp.route("/api/orgs", methods=["POST"])
@jwt_required()
def create_org():
    data = request.get_json()
    name = data.get("name", "").strip()
    parent_id = data.get("parent_id")

    if not name:
        return jsonify({"msg": "机构名称不能为空"}), 400

    if parent_id and not Organization.query.get(parent_id):
        return jsonify({"msg": "上级机构不存在"}), 400

    org = Organization(name=name, parent_id=parent_id or None)
    db.session.add(org)
    db.session.commit()
    return jsonify({"data": {"id": org.id, "name": org.name, "parent_id": org.parent_id}, "msg": "创建成功"})


@org_bp.route("/api/orgs/<int:org_id>", methods=["PUT"])
@jwt_required()
def update_org(org_id):
    org = Organization.query.get(org_id)
    if not org:
        return jsonify({"msg": "机构不存在"}), 404

    data = request.get_json()
    name = data.get("name", "").strip()
    parent_id = data.get("parent_id")

    if not name:
        return jsonify({"msg": "机构名称不能为空"}), 400

    # 不能将自己设为上级，也不能设为自己的子孙
    if parent_id:
        if parent_id == org.id:
            return jsonify({"msg": "上级机构不能是自己"}), 400
        # 检查是否为自己子孙
        descendants = _get_descendant_ids(org.id)
        if parent_id in descendants:
            return jsonify({"msg": "上级机构不能是自己的下级"}), 400

    org.name = name
    org.parent_id = parent_id or None
    db.session.commit()
    return jsonify({"msg": "编辑成功"})


@org_bp.route("/api/orgs/<int:org_id>", methods=["DELETE"])
@jwt_required()
def delete_org(org_id):
    org = Organization.query.get(org_id)
    if not org:
        return jsonify({"msg": "机构不存在"}), 404

    # 子机构上移
    children = Organization.query.filter_by(parent_id=org_id).all()
    for child in children:
        child.parent_id = org.parent_id

    # 单位脱离本机构（不影响考核方案中的任务）
    from models import Unit
    Unit.query.filter_by(org_id=org_id).update({"org_id": None})

    db.session.delete(org)
    db.session.commit()
    return jsonify({"msg": "删除成功"})


@org_bp.route("/api/orgs/batch-delete", methods=["POST"])
@jwt_required()
def batch_delete_orgs():
    data = request.get_json()
    ids = data.get("ids", [])
    if not ids:
        return jsonify({"msg": "请选择要删除的机构"}), 400

    # 单位脱离机构
    from models import Unit
    Unit.query.filter(Unit.org_id.in_(ids)).update({"org_id": None}, synchronize_session=False)

    orgs = Organization.query.filter(Organization.id.in_(ids)).all()
    for org in orgs:
        children = Organization.query.filter_by(parent_id=org.id).all()
        for child in children:
            child.parent_id = org.parent_id
        db.session.delete(org)

    db.session.commit()
    return jsonify({"msg": f"成功删除 {len(orgs)} 个机构"})


@org_bp.route("/api/orgs/import", methods=["POST"])
@jwt_required()
def import_orgs():
    if "file" not in request.files:
        return jsonify({"msg": "请上传文件"}), 400

    file = request.files["file"]
    if not file.filename.endswith((".xlsx", ".xls")):
        return jsonify({"msg": "仅支持 .xlsx 文件"}), 400

    headers, rows = parse_import(file.stream, ["机构名称", "上级机构名称"])
    if headers is None:
        return jsonify({"msg": rows}), 400

    created = 0
    errors = []
    for i, row in enumerate(rows, 2):
        name = row[0] if len(row) > 0 else ""
        parent_name = row[1] if len(row) > 1 else ""

        if not name:
            errors.append(f"第{i}行：机构名称不能为空")
            continue

        parent_id = None
        if parent_name:
            parent = Organization.query.filter_by(name=parent_name).first()
            if not parent:
                errors.append(f"第{i}行：上级机构「{parent_name}」不存在")
                continue
            parent_id = parent.id

        if Organization.query.filter_by(name=name, parent_id=parent_id).first():
            errors.append(f"第{i}行：机构「{name}」已存在")
            continue

        db.session.add(Organization(name=name, parent_id=parent_id))
        created += 1

    db.session.commit()

    result = {"msg": f"成功导入 {created} 个机构"}
    if errors:
        result["errors"] = errors
    return jsonify(result)


@org_bp.route("/api/orgs/export", methods=["GET"])
@jwt_required()
def export_orgs():
    orgs = Organization.query.order_by(Organization.id).all()
    rows = []
    for o in orgs:
        parent_name = ""
        if o.parent_id:
            parent = Organization.query.get(o.parent_id)
            parent_name = parent.name if parent else ""
        rows.append([o.name, parent_name])

    output = export_xlsx(["机构名称", "上级机构名称"], rows)
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="组织机构.xlsx")


@org_bp.route("/api/orgs/template", methods=["GET"])
@jwt_required()
def download_template():
    output = export_xlsx(["机构名称", "上级机构名称"], [["示例机构", ""]])
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="组织机构导入模板.xlsx")


def _get_descendant_ids(org_id):
    """获取机构的所有子孙节点 ID"""
    ids = set()
    children = Organization.query.filter_by(parent_id=org_id).all()
    for child in children:
        ids.add(child.id)
        ids.update(_get_descendant_ids(child.id))
    return ids
