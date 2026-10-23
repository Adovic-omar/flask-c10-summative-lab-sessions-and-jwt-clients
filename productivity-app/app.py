import os
from functools import wraps

from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_migrate import Migrate
from sqlalchemy.exc import IntegrityError

from models import db, bcrypt, User, Note


app = Flask(__name__)

# Application configuration
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "development-secret-key-change-this"
)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///productivity.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Allow the frontend to send session cookies
CORS(
    app,
    supports_credentials=True,
    origins=[
        "http://localhost:3000",
        "http://localhost:5173"
    ]
)

# Initialize extensions
db.init_app(app)
bcrypt.init_app(app)
migrate = Migrate(app, db)


# Authentication decorator
def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        user_id = session.get("user_id")

        if user_id is None:
            return jsonify({"error": "Authentication required"}), 401

        user = db.session.get(User, user_id)

        if user is None:
            session.clear()
            return jsonify({"error": "Authentication required"}), 401

        return view_function(*args, **kwargs)

    return wrapped_view


# Get the currently logged-in user
def get_current_user():
    user_id = session.get("user_id")

    if user_id is None:
        return None

    return db.session.get(User, user_id)


# Home route
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "Productivity App API is running"
    }), 200


# Register a new user
@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}

    username = data.get("username")
    password = data.get("password")

    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify({
            "error": "Username and password are required"
        }), 400

    username = username.strip()

    if not username or not password:
        return jsonify({
            "error": "Username and password cannot be empty"
        }), 400

    if len(username) > 80:
        return jsonify({
            "error": "Username must be 80 characters or fewer"
        }), 400

    if len(password) < 8:
        return jsonify({
            "error": "Password must contain at least 8 characters"
        }), 400

    user = User(username=username)
    user.set_password(password)

    db.session.add(user)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            "error": "Username already exists"
        }), 409

    return jsonify({
        "message": "User registered successfully",
        "user": user.to_dict()
    }), 201


# Log in an existing user
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    username = data.get("username")
    password = data.get("password")

    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify({
            "error": "Username and password are required"
        }), 400

    user = User.query.filter_by(username=username.strip()).first()

    if user is None or not user.check_password(password):
        return jsonify({
            "error": "Invalid username or password"
        }), 401

    session.clear()
    session["user_id"] = user.id

    return jsonify({
        "message": "Login successful",
        "user": user.to_dict()
    }), 200


# Check the current login session
@app.route("/check_session", methods=["GET"])
@login_required
def check_session():
    user = get_current_user()

    return jsonify({
        "user": user.to_dict()
    }), 200


# Log out
@app.route("/logout", methods=["DELETE"])
@login_required
def logout():
    session.clear()

    return jsonify({
        "message": "Logged out successfully"
    }), 200


# Get all notes belonging to the logged-in user
# Supports pagination with page and per_page query parameters
@app.route("/notes", methods=["GET"])
@login_required
def get_notes():
    user = get_current_user()

    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 10))
    except ValueError:
        return jsonify({
            "error": "Page and per_page must be integers"
        }), 400

    if page < 1 or per_page < 1:
        return jsonify({
            "error": "Page and per_page must be positive integers"
        }), 400

    per_page = min(per_page, 100)

    pagination = Note.query.filter_by(
        user_id=user.id
    ).order_by(
        Note.id.desc()
    ).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    return jsonify({
        "notes": [note.to_dict() for note in pagination.items],
        "pagination": {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages
        }
    }), 200


# Get one note belonging to the logged-in user
@app.route("/notes/<int:note_id>", methods=["GET"])
@login_required
def get_note(note_id):
    user = get_current_user()

    note = Note.query.filter_by(
        id=note_id,
        user_id=user.id
    ).first()

    if note is None:
        return jsonify({"error": "Note not found"}), 404

    return jsonify(note.to_dict()), 200


# Create a note for the logged-in user
@app.route("/notes", methods=["POST"])
@login_required
def create_note():
    user = get_current_user()
    data = request.get_json(silent=True) or {}

    title = data.get("title")
    content = data.get("content")

    if not isinstance(title, str) or not isinstance(content, str):
        return jsonify({
            "error": "Title and content are required"
        }), 400

    title = title.strip()
    content = content.strip()

    if not title or not content:
        return jsonify({
            "error": "Title and content cannot be empty"
        }), 400

    if len(title) > 150:
        return jsonify({
            "error": "Title must be 150 characters or fewer"
        }), 400

    note = Note(
        title=title,
        content=content,
        user_id=user.id
    )

    db.session.add(note)
    db.session.commit()

    return jsonify({
        "message": "Note created successfully",
        "note": note.to_dict()
    }), 201


# Update a note belonging to the logged-in user
@app.route("/notes/<int:note_id>", methods=["PATCH"])
@login_required
def update_note(note_id):
    user = get_current_user()

    note = Note.query.filter_by(
        id=note_id,
        user_id=user.id
    ).first()

    if note is None:
        return jsonify({"error": "Note not found"}), 404

    data = request.get_json(silent=True)

    if not isinstance(data, dict) or not data:
        return jsonify({
            "error": "Provide note fields to update"
        }), 400

    if "title" in data:
        if not isinstance(data["title"], str):
            return jsonify({"error": "Title must be text"}), 400

        title = data["title"].strip()

        if not title or len(title) > 150:
            return jsonify({
                "error": "Title must contain 1 to 150 characters"
            }), 400

        note.title = title

    if "content" in data:
        if not isinstance(data["content"], str):
            return jsonify({"error": "Content must be text"}), 400

        content = data["content"].strip()

        if not content:
            return jsonify({
                "error": "Content cannot be empty"
            }), 400

        note.content = content

    db.session.commit()

    return jsonify({
        "message": "Note updated successfully",
        "note": note.to_dict()
    }), 200


# Delete a note belonging to the logged-in user
@app.route("/notes/<int:note_id>", methods=["DELETE"])
@login_required
def delete_note(note_id):
    user = get_current_user()

    note = Note.query.filter_by(
        id=note_id,
        user_id=user.id
    ).first()

    if note is None:
        return jsonify({"error": "Note not found"}), 404

    db.session.delete(note)
    db.session.commit()

    return jsonify({
        "message": "Note deleted successfully"
    }), 200


if __name__ == "__main__":
    app.run(debug=True)
