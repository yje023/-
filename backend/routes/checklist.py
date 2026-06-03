"""清单管理 — 履职事项清单（镇街/部门）"""
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required
from models import db, ChecklistItem, Unit, Organization
from sqlalchemy import or_
from utils.xlsx_handler import export_xlsx, parse_import

checklist_bp = Blueprint("checklist", __name__)


def _item_to_dict(item):
    return {
        "id": item.id,
        "org_category": item.org_category,
        "item_category": item.item_category,
        "seq_num": item.seq_num,
        "name": item.name,
        "unit_id": item.unit_id,
        "unit_name": item.unit.name if item.unit else "",
        "street_unit_id": item.street_unit_id,
        "street_unit_name": item.street_unit.name if item.street_unit else "",
        "superior_dept_duty": item.superior_dept_duty or "",
        "street_duty": item.street_duty or "",
        "工作方式": getattr(item, "工作方式", "") or "",
        "is_synced": item.is_synced,
        "source_item_id": item.source_item_id,
        "created_at": str(item.created_at) if item.created_at else None,
    }


def _sync_to_dept(item):
    """镇街创建配合/收回事项 → 同步到对应部门"""
    if item.org_category != "street" or item.item_category == "basic":
        return
    if item.is_synced:
        return
    # unit_id 存储的是对应部门单位
    dept_unit_id = item.unit_id
    synced = ChecklistItem(
        org_category="dept",
        item_category=item.item_category,
        seq_num=item.seq_num,
        name=item.name,
        unit_id=dept_unit_id,
        street_unit_id=item.street_unit_id,
        superior_dept_duty=item.superior_dept_duty,
        street_duty=item.street_duty,
        工作方式=getattr(item, "工作方式", "") or "",
        is_synced=True,
        source_item_id=item.id,
    )
    db.session.add(synced)


def _delete_synced(source_item_id):
    """删除同步副本"""
    if source_item_id:
        ChecklistItem.query.filter_by(source_item_id=source_item_id, is_synced=True).delete()


def _update_synced(item):
    """更新同步副本"""
    synced = ChecklistItem.query.filter_by(source_item_id=item.id, is_synced=True).first()
    if synced:
        synced.seq_num = item.seq_num
        synced.name = item.name
        synced.street_unit_id = item.street_unit_id
        synced.superior_dept_duty = item.superior_dept_duty
        synced.street_duty = item.street_duty
        setattr(synced, "工作方式", getattr(item, "工作方式", "") or "")


@checklist_bp.route("/api/checklist-items", methods=["GET"])
@jwt_required()
def list_items():
    org_category = request.args.get("org_category", "")
    item_category = request.args.get("item_category", "")
    unit_id = request.args.get("unit_id", type=int)
    search = request.args.get("search", "")
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 200, type=int)
    page_size = min(page_size, 500)

    q = ChecklistItem.query
    if org_category:
        q = q.filter(ChecklistItem.org_category == org_category)
    if item_category:
        q = q.filter(ChecklistItem.item_category == item_category)
    if unit_id:
        q = q.filter(
            or_(
                ChecklistItem.unit_id == unit_id,
                ChecklistItem.street_unit_id == unit_id,
            )
        )
    if search:
        q = q.filter(ChecklistItem.name.contains(search))

    total = q.count()
    items = q.order_by(ChecklistItem.seq_num, ChecklistItem.id).offset((page - 1) * page_size).limit(page_size).all()
    return jsonify({"data": {
        "items": [_item_to_dict(i) for i in items],
        "total": total, "page": page, "page_size": page_size,
    }})


@checklist_bp.route("/api/checklist-items", methods=["POST"])
@jwt_required()
def create_item():
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"msg": "事项名称不能为空"}), 400

    item = ChecklistItem(
        org_category=data.get("org_category", "street"),
        item_category=data.get("item_category", "basic"),
        seq_num=data.get("seq_num", 0),
        name=data["name"].strip(),
        unit_id=data.get("unit_id", 0),
        street_unit_id=data.get("street_unit_id") or None,
        superior_dept_duty=data.get("superior_dept_duty", ""),
        street_duty=data.get("street_duty", ""),
    )
    if "工作方式" in data:
        setattr(item, "工作方式", data["工作方式"])
    db.session.add(item)
    db.session.flush()  # 获取 item.id
    _sync_to_dept(item)
    db.session.commit()
    return jsonify({"data": _item_to_dict(item), "msg": "创建成功"})


@checklist_bp.route("/api/checklist-items/<int:item_id>", methods=["PUT"])
@jwt_required()
def update_item(item_id):
    item = ChecklistItem.query.get(item_id)
    if not item:
        return jsonify({"msg": "事项不存在"}), 404
    if item.is_synced:
        return jsonify({"msg": "同步条目不可编辑"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"msg": "无效数据"}), 400
    if "name" in data and data["name"]:
        item.name = data["name"].strip()
    if "seq_num" in data:
        item.seq_num = data["seq_num"]
    if "unit_id" in data:
        item.unit_id = data["unit_id"]
    if "street_unit_id" in data:
        item.street_unit_id = data["street_unit_id"] or None
    if "superior_dept_duty" in data:
        item.superior_dept_duty = data["superior_dept_duty"]
    if "street_duty" in data:
        item.street_duty = data["street_duty"]
    if "工作方式" in data:
        setattr(item, "工作方式", data["工作方式"])

    _update_synced(item)
    db.session.commit()
    return jsonify({"data": _item_to_dict(item), "msg": "更新成功"})


@checklist_bp.route("/api/checklist-items/<int:item_id>", methods=["DELETE"])
@jwt_required()
def delete_item(item_id):
    item = ChecklistItem.query.get(item_id)
    if not item:
        return jsonify({"msg": "事项不存在"}), 404
    if item.is_synced:
        return jsonify({"msg": "同步条目不可删除"}), 403

    _delete_synced(item.id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({"msg": "删除成功"})


@checklist_bp.route("/api/checklist-items/batch-delete", methods=["POST"])
@jwt_required()
def batch_delete_items():
    data = request.get_json()
    if not data or not data.get("ids"):
        return jsonify({"msg": "请选择要删除的事项"}), 400
    ids = data["ids"]
    items = ChecklistItem.query.filter(ChecklistItem.id.in_(ids), ChecklistItem.is_synced == False).all()
    for item in items:
        _delete_synced(item.id)
        db.session.delete(item)
    db.session.commit()
    return jsonify({"msg": f"成功删除 {len(items)} 个事项"})


@checklist_bp.route("/api/checklist-items/import", methods=["POST"])
@jwt_required()
def import_items():
    if "file" not in request.files:
        return jsonify({"msg": "请上传文件"}), 400
    file = request.files["file"]
    if not file.filename.endswith((".xlsx", ".xls")):
        return jsonify({"msg": "仅支持 .xlsx 文件"}), 400

    headers, rows = parse_import(file.stream, [
        "类别(street/dept)", "事项类型(basic/cooperative/recall)",
        "序号", "事项名称", "关联单位", "来源镇街",
        "上级部门职责", "镇街配合职责", "工作方式"
    ])
    if headers is None:
        return jsonify({"msg": rows}), 400

    errors = []
    created = 0
    for i, row in enumerate(rows, start=2):
        org_category = (row[0] or "").strip()
        item_category = (row[1] or "").strip()
        try:
            seq_num = int(row[2]) if row[2] else 0
        except ValueError:
            seq_num = 0
        name = (row[3] or "").strip()
        unit_name = (row[4] or "").strip() if len(row) > 4 else ""
        street_name = (row[5] or "").strip() if len(row) > 5 else ""
        superior_dept_duty = (row[6] or "").strip() if len(row) > 6 else ""
        street_duty = (row[7] or "").strip() if len(row) > 7 else ""
        工作方式 = (row[8] or "").strip() if len(row) > 8 else ""

        if not name:
            continue
        if org_category not in ("street", "dept"):
            errors.append(f"第{i}行：类别须为 street 或 dept")
            continue
        if item_category not in ("basic", "cooperative", "recall"):
            errors.append(f"第{i}行：事项类型须为 basic/cooperative/recall")
            continue

        unit = Unit.query.filter_by(name=unit_name).first() if unit_name else None
        street_unit = Unit.query.filter_by(name=street_name).first() if street_name else None

        item = ChecklistItem(
            org_category=org_category,
            item_category=item_category,
            seq_num=seq_num,
            name=name,
            unit_id=unit.id if unit else 0,
            street_unit_id=street_unit.id if street_unit else None,
            superior_dept_duty=superior_dept_duty,
            street_duty=street_duty,
        )
        if 工作方式:
            setattr(item, "工作方式", 工作方式)
        db.session.add(item)
        db.session.flush()
        _sync_to_dept(item)
        created += 1

    if errors:
        db.session.rollback()
        return jsonify({"msg": f"导入失败：{'; '.join(errors[:10])}"}), 400

    db.session.commit()
    return jsonify({"msg": f"成功导入 {created} 个事项"})


@checklist_bp.route("/api/checklist-items/export", methods=["GET"])
@jwt_required()
def export_items():
    org_category = request.args.get("org_category", "")
    item_category = request.args.get("item_category", "")

    q = ChecklistItem.query
    if org_category:
        q = q.filter(ChecklistItem.org_category == org_category)
    if item_category:
        q = q.filter(ChecklistItem.item_category == item_category)
    items = q.order_by(ChecklistItem.org_category, ChecklistItem.item_category, ChecklistItem.seq_num).all()

    headers = ["类别", "事项类型", "序号", "事项名称", "关联单位", "来源镇街",
               "上级部门职责", "镇街配合职责", "工作方式", "是否同步"]
    rows = []
    for item in items:
        rows.append([
            item.org_category,
            item.item_category,
            item.seq_num,
            item.name,
            item.unit.name if item.unit else "",
            item.street_unit.name if item.street_unit else "",
            item.superior_dept_duty or "",
            item.street_duty or "",
            getattr(item, "工作方式", "") or "",
            "是" if item.is_synced else "否",
        ])
    output = export_xlsx(headers, rows)
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="履职事项清单.xlsx")


@checklist_bp.route("/api/checklist-items/template", methods=["GET"])
@jwt_required()
def download_template():
    output = export_xlsx(
        ["类别(street/dept)", "事项类型(basic/cooperative/recall)",
         "序号", "事项名称", "关联单位", "来源镇街",
         "上级部门职责", "镇街配合职责", "工作方式"],
        [["street", "basic", "1", "示例基本事项", "城东街道", "", "", "", ""]]
    )
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="履职事项清单导入模板.xlsx")
