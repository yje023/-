from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.dashboard_service import get_dashboard_overview

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
