from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from services.quality_checker import run_quality_check

qc_bp = Blueprint("quality_check", __name__)


@qc_bp.route("/api/quality-check/run", methods=["POST"])
@jwt_required()
def run_check():
    """对指定方案执行质检"""
    data = request.get_json() or {}
    plan_id = data.get("plan_id")
    if not plan_id:
        return jsonify({"msg": "请选择考核方案"}), 400

    results = run_quality_check(plan_id=plan_id)
    return jsonify({"data": results, "msg": f"检测完成，共发现 {results['total_issues']} 个问题"})
