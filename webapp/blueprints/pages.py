"""Public pages blueprint."""

from flask import Blueprint, render_template

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def home():
    """Home page."""
    return render_template("home.html")


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
