from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required
from models import db, AssessmentResult, Cadre
from utils.xlsx_handler import export_xlsx, parse_import

result_bp = Blueprint("assessment_result", __name__)


def _result_to_dict(r):
    return {
        "id": r.id,
        "cadre_id": r.cadre_id,
        "cadre_name": r.cadre.name if r.cadre else "",
        "unit_name": r.cadre.unit.name if r.cadre and r.cadre.unit else "",
        "plan_year": r.plan_year,
        "position_type": r.position_type,
        "total_score": r.total_score,
        "has_violation": r.has_violation,
        "is_excellent": r.is_excellent,
        "rank": r.rank,
    }


@result_bp.route("/api/assessment-results", methods=["GET"])
@jwt_required()
def list_results():
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    page_size = min(page_size, 200)
    plan_year = request.args.get("plan_year", type=int)
    position_type = request.args.get("position_type", "")

    q = AssessmentResult.query
    if plan_year:
        q = q.filter(AssessmentResult.plan_year == plan_year)
    if position_type:
        q = q.filter(AssessmentResult.position_type == position_type)
    total = q.count()
    items = q.order_by(AssessmentResult.rank.asc().nullslast(), AssessmentResult.total_score.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    return jsonify({"data": {
        "items": [_result_to_dict(r) for r in items],
        "total": total, "page": page, "page_size": page_size,
    }})


@result_bp.route("/api/assessment-results/import", methods=["POST"])
@jwt_required()
def import_results():
    if "file" not in request.files:
        return jsonify({"msg": "请上传文件"}), 400
    file = request.files["file"]
    if not file.filename.endswith((".xlsx", ".xls")):
        return jsonify({"msg": "仅支持 .xlsx 文件"}), 400

    headers, rows = parse_import(file.stream, [
        "干部姓名", "考核年度", "职务类型", "考核得分", "违法违纪组织处理", "班子是否评优", "排名"
    ])
    if headers is None:
        return jsonify({"msg": rows}), 400

    created = 0
    errors = []
    for i, row in enumerate(rows, start=2):
        name = (row[0] or "").strip()
        if not name:
            continue
        cadre = Cadre.query.filter_by(name=name).first()
        if not cadre:
            errors.append(f"第{i}行：干部「{name}」不存在")
            continue

        r = AssessmentResult(cadre_id=cadre.id)
        try:
            r.plan_year = int(row[1]) if len(row) > 1 and row[1] else None
        except Exception:
            errors.append(f"第{i}行：考核年度格式错误")
            continue
        if len(row) > 2 and row[2]:
            r.position_type = str(row[2]).strip()
        try:
            r.total_score = float(row[3]) if len(row) > 3 and row[3] else None
        except Exception:
            pass
        if len(row) > 4 and row[4]:
            val = str(row[4]).strip()
            r.has_violation = val in ("是", "有", "1", "true", "True")
        if len(row) > 5 and row[5]:
            val = str(row[5]).strip()
            r.is_excellent = val in ("是", "有", "优", "1", "true", "True")
        try:
            r.rank = int(row[6]) if len(row) > 6 and row[6] else None
        except Exception:
            pass

        db.session.add(r)
        created += 1

    if errors:
        db.session.rollback()
        return jsonify({"msg": f"导入失败：{'；'.join(errors[:10])}"}), 400

    db.session.commit()
    return jsonify({"msg": f"成功导入 {created} 条考核结果"})


@result_bp.route("/api/assessment-results/export", methods=["GET"])
@jwt_required()
def export_results():
    plan_year = request.args.get("plan_year", type=int)
    position_type = request.args.get("position_type", "")
    q = AssessmentResult.query
    if plan_year:
        q = q.filter(AssessmentResult.plan_year == plan_year)
    if position_type:
        q = q.filter(AssessmentResult.position_type == position_type)
    results = q.order_by(AssessmentResult.rank.asc().nullslast()).all()

    rows = []
    for r in results:
        rows.append([
            r.cadre.name if r.cadre else "",
            r.plan_year,
            r.position_type or "",
            r.total_score or "",
            "是" if r.has_violation else "否",
            "是" if r.is_excellent else "否",
            r.rank or "",
        ])
    output = export_xlsx(
        ["干部姓名", "考核年度", "职务类型", "考核得分", "违法违纪组织处理", "班子是否评优", "排名"],
        rows
    )
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="考核结果.xlsx")


@result_bp.route("/api/assessment-results/template", methods=["GET"])
@jwt_required()
def download_template():
    output = export_xlsx(
        ["干部姓名", "考核年度", "职务类型", "考核得分", "违法违纪组织处理", "班子是否评优", "排名"],
        [["张三", "2025", "正职", "95.5", "否", "是", "1"]]
    )
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="考核结果导入模板.xlsx")


@result_bp.route("/api/assessment-results/batch-delete", methods=["POST"])
@jwt_required()
def batch_delete_results():
    data = request.get_json()
    if not data or not data.get("ids"):
        return jsonify({"msg": "请选择要删除的记录"}), 400
    AssessmentResult.query.filter(AssessmentResult.id.in_(data["ids"])).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"msg": f"成功删除 {len(data['ids'])} 条记录"})
