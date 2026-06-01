from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required
from models import db, Cadre, Unit
from utils.xlsx_handler import export_xlsx, parse_import
from datetime import datetime

cadre_bp = Blueprint("cadre", __name__)


def _cadre_to_dict(c):
    return {
        "id": c.id,
        "name": c.name,
        "unit_id": c.unit_id,
        "unit_name": c.unit.name if c.unit else "",
        "gender": c.gender,
        "birth_date": str(c.birth_date) if c.birth_date else None,
        "education": c.education,
        "fulltime_education": c.fulltime_education,
        "political_status": c.political_status,
        "ethnicity": c.ethnicity,
        "position_type": c.position_type,
        "specialty": c.specialty,
        "expertise": c.expertise,
        "created_at": str(c.created_at) if c.created_at else None,
    }


@cadre_bp.route("/api/cadres", methods=["GET"])
@jwt_required()
def list_cadres():
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    page_size = min(page_size, 200)
    search = request.args.get("search", "")
    unit_id = request.args.get("unit_id", type=int)

    q = Cadre.query
    if search:
        q = q.filter(Cadre.name.contains(search))
    if unit_id:
        q = q.filter(Cadre.unit_id == unit_id)
    total = q.count()
    items = q.order_by(Cadre.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return jsonify({"data": {
        "items": [_cadre_to_dict(c) for c in items],
        "total": total, "page": page, "page_size": page_size,
    }})


@cadre_bp.route("/api/cadres", methods=["POST"])
@jwt_required()
def create_cadre():
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"msg": "姓名不能为空"}), 400

    c = Cadre()
    _fill_cadre(c, data)
    db.session.add(c)
    db.session.commit()
    return jsonify({"data": _cadre_to_dict(c), "msg": "创建成功"})


@cadre_bp.route("/api/cadres/<int:cadre_id>", methods=["PUT"])
@jwt_required()
def update_cadre(cadre_id):
    c = Cadre.query.get(cadre_id)
    if not c:
        return jsonify({"msg": "干部不存在"}), 404
    data = request.get_json()
    if not data:
        return jsonify({"msg": "无效数据"}), 400
    _fill_cadre(c, data)
    db.session.commit()
    return jsonify({"data": _cadre_to_dict(c), "msg": "更新成功"})


@cadre_bp.route("/api/cadres/<int:cadre_id>", methods=["DELETE"])
@jwt_required()
def delete_cadre(cadre_id):
    c = Cadre.query.get(cadre_id)
    if not c:
        return jsonify({"msg": "干部不存在"}), 404
    db.session.delete(c)
    db.session.commit()
    return jsonify({"msg": "删除成功"})


@cadre_bp.route("/api/cadres/batch-delete", methods=["POST"])
@jwt_required()
def batch_delete_cadres():
    data = request.get_json()
    if not data or not data.get("ids"):
        return jsonify({"msg": "请选择要删除的干部"}), 400
    Cadre.query.filter(Cadre.id.in_(data["ids"])).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"msg": f"成功删除 {len(data['ids'])} 名干部"})


@cadre_bp.route("/api/cadres/import", methods=["POST"])
@jwt_required()
def import_cadres():
    if "file" not in request.files:
        return jsonify({"msg": "请上传文件"}), 400
    file = request.files["file"]
    if not file.filename.endswith((".xlsx", ".xls")):
        return jsonify({"msg": "仅支持 .xlsx 文件"}), 400

    headers, rows = parse_import(file.stream, [
        "姓名", "单位名称", "性别", "出生日期", "最高学历", "全日制学历",
        "政治面貌", "民族", "职务类型", "专业领域", "擅长领域"
    ])
    if headers is None:
        return jsonify({"msg": rows}), 400

    created = 0
    errors = []
    for i, row in enumerate(rows, start=2):
        name = (row[0] or "").strip()
        if not name:
            continue
        unit_name = (row[1] or "").strip() if len(row) > 1 else ""
        unit = Unit.query.filter_by(name=unit_name).first() if unit_name else None
        if unit_name and not unit:
            errors.append(f"第{i}行：单位「{unit_name}」不存在")
            continue

        c = Cadre(name=name, unit_id=unit.id if unit else None)
        if len(row) > 2 and row[2]:
            c.gender = str(row[2]).strip()
        if len(row) > 3 and row[3]:
            try:
                if hasattr(row[3], 'strftime'):
                    c.birth_date = row[3]
                else:
                    c.birth_date = datetime.strptime(str(row[3]).strip()[:10], "%Y-%m-%d").date()
            except Exception:
                pass
        if len(row) > 4:
            c.education = str(row[4]).strip() if row[4] else None
        if len(row) > 5:
            c.fulltime_education = str(row[5]).strip() if row[5] else None
        if len(row) > 6:
            c.political_status = str(row[6]).strip() if row[6] else None
        if len(row) > 7:
            c.ethnicity = str(row[7]).strip() if row[7] else None
        if len(row) > 8:
            c.position_type = str(row[8]).strip() if row[8] else None
        if len(row) > 9:
            c.specialty = str(row[9]).strip() if row[9] else None
        if len(row) > 10:
            c.expertise = str(row[10]).strip() if row[10] else None

        db.session.add(c)
        created += 1

    if errors:
        db.session.rollback()
        return jsonify({"msg": f"导入失败：{'；'.join(errors[:10])}"}), 400

    db.session.commit()
    return jsonify({"msg": f"成功导入 {created} 名干部"})


@cadre_bp.route("/api/cadres/export", methods=["GET"])
@jwt_required()
def export_cadres():
    cadres = Cadre.query.order_by(Cadre.id).all()
    rows = []
    for c in cadres:
        rows.append([
            c.name,
            c.unit.name if c.unit else "",
            c.gender,
            str(c.birth_date) if c.birth_date else "",
            c.education or "",
            c.fulltime_education or "",
            c.political_status or "",
            c.ethnicity or "",
            c.position_type or "",
            c.specialty or "",
            c.expertise or "",
        ])
    output = export_xlsx(
        ["姓名", "单位名称", "性别", "出生日期", "最高学历", "全日制学历",
         "政治面貌", "民族", "职务类型", "专业领域", "擅长领域"],
        rows
    )
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="干部列表.xlsx")


@cadre_bp.route("/api/cadres/template", methods=["GET"])
@jwt_required()
def download_template():
    output = export_xlsx(
        ["姓名", "单位名称", "性别", "出生日期", "最高学历", "全日制学历",
         "政治面貌", "民族", "职务类型", "专业领域", "擅长领域"],
        [["张三", "示例单位", "男", "1985-06-15", "研究生", "硕士研究生",
          "中共党员", "汉族", "正职", "公共管理", "行政审批,政策研究"]]
    )
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="干部导入模板.xlsx")


def _fill_cadre(c, data):
    if "name" in data and data["name"]:
        c.name = data["name"].strip()
    if "unit_id" in data:
        c.unit_id = data["unit_id"] or None
    if "gender" in data:
        c.gender = data["gender"]
    if "birth_date" in data and data["birth_date"]:
        try:
            c.birth_date = datetime.strptime(data["birth_date"][:10], "%Y-%m-%d").date()
        except Exception:
            pass
    if "education" in data:
        c.education = data["education"]
    if "fulltime_education" in data:
        c.fulltime_education = data["fulltime_education"]
    if "political_status" in data:
        c.political_status = data["political_status"]
    if "ethnicity" in data:
        c.ethnicity = data["ethnicity"]
    if "position_type" in data:
        c.position_type = data["position_type"]
    if "specialty" in data:
        c.specialty = data["specialty"]
    if "expertise" in data:
        c.expertise = data["expertise"]
