"""
Auth Blueprint

REST API and page endpoints for user authentication.

Endpoints:
- POST /api/auth/register - Create account
- POST /api/auth/login - Login
- POST /api/auth/logout - Logout
- GET /api/auth/me - Current user info
- GET /login - Login page
- GET /register - Register page
"""

import logging

from flask import Blueprint, jsonify, redirect, render_template, request
from flask_bcrypt import check_password_hash, generate_password_hash
from flask_login import current_user, login_required, login_user, logout_user

from webapp.models import Team, User, db
from webapp.utils import sanitize_input, validate_email

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login")
def login_page():
    """Render login page."""
    if current_user.is_authenticated:
        return redirect("/")
    return render_template("auth/login.html")


@auth_bp.route("/register")
def register_page():
    """Render registration page."""
    if current_user.is_authenticated:
        return redirect("/")
    return render_template("auth/register.html")


@auth_bp.route("/api/auth/register", methods=["POST"])
def api_register():
    """
    Register a new user account.

    Request (JSON):
        - email: User email (required)
        - password: Password (required, min 8 chars)
        - name: Display name (required)

    Response:
        - success: boolean
        - user: User info dict
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        name = sanitize_input((data.get("name") or "").strip())

        if not email or not validate_email(email):
            return jsonify({"error": "Valid email is required"}), 400

        if len(password) < 8:
            return jsonify({"error": "Password must be at least 8 characters"}), 400

        if not name or len(name) < 1:
            return jsonify({"error": "Name is required"}), 400

        if len(name) > 255:
            return jsonify({"error": "Name must be 255 characters or less"}), 400

        existing = User.query.filter_by(email=email).first()
        if existing:
            return jsonify({"error": "An account with this email already exists"}), 409

        pw_hash = generate_password_hash(password).decode("utf-8")

        user = User(
            email=email,
            password_hash=pw_hash,
            name=name,
            role="owner",
        )
        db.session.add(user)
        db.session.flush()

        team = Team(
            name=f"{name}'s Team",
            owner_id=user.id,
        )
        db.session.add(team)
        db.session.flush()

        user.team_id = team.id
        db.session.commit()

        login_user(user)

        return jsonify({"success": True, "user": user.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        logger.exception(f"Registration error: {e}")
        return jsonify({"error": "Registration failed"}), 500


@auth_bp.route("/api/auth/login", methods=["POST"])
def api_login():
    """
    Login with email and password.

    Request (JSON):
        - email: User email (required)
        - password: Password (required)

    Response:
        - success: boolean
        - user: User info dict
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400

        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "Invalid email or password"}), 401

        if not user.is_active:
            return jsonify({"error": "Account is deactivated"}), 403

        login_user(user)

        return jsonify({"success": True, "user": user.to_dict()})

    except Exception as e:
        logger.exception(f"Login error: {e}")
        return jsonify({"error": "Login failed"}), 500


@auth_bp.route("/api/auth/logout", methods=["POST"])
@login_required
def api_logout():
    """Logout current user."""
    logout_user()
    return jsonify({"success": True})


@auth_bp.route("/api/auth/me", methods=["GET"])
@login_required
def api_me():
    """
    Get current user info.

    Response:
        - success: boolean
        - user: User info dict with role
    """
    return jsonify({"success": True, "user": current_user.to_dict()})
