"""Public pages blueprint."""

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def home():
    """Home page — redirects authenticated users to dashboard."""
    if current_user.is_authenticated:
        return redirect(url_for("pages.dashboard"))
    return render_template("home.html")


@pages_bp.route("/dashboard")
@login_required
def dashboard():
    """Authenticated user dashboard."""
    return render_template("dashboard.html")


@pages_bp.route("/chat")
@login_required
def chat_page():
    """Chat interface page."""
    return render_template("chat.html")


@pages_bp.route("/pricing")
def pricing():
    """Pricing page."""
    return render_template("pricing.html")


@pages_bp.route("/features")
def features():
    """Features page."""
    return render_template("features.html")


@pages_bp.route("/contact")
def contact():
    """Contact page."""
    return render_template("contact.html")


@pages_bp.route("/book-setup")
def book_setup():
    """Book setup call page."""
    return render_template("book_setup.html")
