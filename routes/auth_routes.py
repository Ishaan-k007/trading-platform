from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError

from services.auth_service import AuthService
from schemas.auth_schemas import RegisterSchema, LoginSchema

auth_bp = Blueprint("auth", __name__)

register_schema = RegisterSchema()
login_schema    = LoginSchema()
auth_service    = AuthService()


@auth_bp.route("/register", methods=["POST"])
def register():
    try:
        data = register_schema.load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": e.messages}}), 422

    try:
        user = auth_service.register(
            email=data["email"],
            username=data["username"],
            password=data["password"],
        )
    except IntegrityError:
        return jsonify({"error": {"code": "ALREADY_EXISTS",
                                  "message": "Email or username already taken."}}), 409

    return jsonify({"message": "Registered successfully.", "user_id": user.id}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    try:
        data = login_schema.load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": e.messages}}), 422

    tokens = auth_service.login(
        username=data["username"],
        password=data["password"],
    )

    return jsonify(tokens), 200


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    user_id      = get_jwt_identity()
    access_token = create_access_token(identity=user_id)
    return jsonify({"access_token": access_token}), 200
