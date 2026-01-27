"""API routes."""

from flask import Blueprint, jsonify, request

api_bp = Blueprint("api", __name__)


@api_bp.route("/users", methods=["GET"])
def get_users():
    """Get all users."""
    # Placeholder - would normally query database
    users = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]
    return jsonify(users)


@api_bp.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id: int):
    """Get a specific user by ID."""
    # Placeholder - would normally query database
    user = {"id": user_id, "name": "Example User"}
    return jsonify(user)


@api_bp.route("/users", methods=["POST"])
def create_user():
    """Create a new user."""
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "Name is required"}), 400

    # Placeholder - would normally insert into database
    new_user = {"id": 3, "name": data["name"]}
    return jsonify(new_user), 201
