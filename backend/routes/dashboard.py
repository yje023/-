from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.dashboard_service import (
    get_dashboard_overview, get_cadre_stats, get_task_progress,
    get_task_flow, get_assessment_results, get_task_decomposition,
)

dashboard_bp = Blueprint("dashboard", __name__)


def _get_user(user_id):
    from models import User
    return User.query.get(user_id)


@dashboard_bp.route("/api/dashboard/overview", methods=["GET"])
@jwt_required()
def overview():
    user = _get_user(int(get_jwt_identity()))
    plan_id = request.args.get("plan_id", type=int)
    data = get_dashboard_overview(plan_id=plan_id, user=user)
    return jsonify({"data": data})


@dashboard_bp.route("/api/dashboard/cadre-stats", methods=["GET"])
@jwt_required()
def cadre_stats():
    data = get_cadre_stats()
    return jsonify({"data": data})


@dashboard_bp.route("/api/dashboard/task-progress", methods=["GET"])
@jwt_required()
def task_progress():
    user = _get_user(int(get_jwt_identity()))
    plan_id = request.args.get("plan_id", type=int)
    data = get_task_progress(plan_id=plan_id, user=user)
    return jsonify({"data": data})


@dashboard_bp.route("/api/dashboard/flow", methods=["GET"])
@jwt_required()
def task_flow():
    user = _get_user(int(get_jwt_identity()))
    plan_id = request.args.get("plan_id", type=int)
    data = get_task_flow(plan_id=plan_id, user=user)
    return jsonify({"data": data})


@dashboard_bp.route("/api/dashboard/results", methods=["GET"])
@jwt_required()
def assessment_results():
    plan_year = request.args.get("plan_year", type=int)
    position_type = request.args.get("position_type", "")
    data = get_assessment_results(plan_year=plan_year, position_type=position_type)
    return jsonify({"data": data})


@dashboard_bp.route("/api/dashboard/task-decomp", methods=["GET"])
@jwt_required()
def task_decomp():
    user = _get_user(int(get_jwt_identity()))
    plan_id = request.args.get("plan_id", type=int)
    data = get_task_decomposition(plan_id=plan_id, user=user)
    return jsonify({"data": data})
