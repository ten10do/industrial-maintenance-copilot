import pytest

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.base import RoleEnum
from app.models.user import User


def create_demo_user(db) -> User:
    user = User(
        email="admin@example.com",
        full_name="演示管理员",
        hashed_password=hash_password("Demo123456"),
        role=RoleEnum.admin,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_production_rejects_demo_account_login(client, db, monkeypatch):
    create_demo_user(db)
    monkeypatch.setattr(settings, "APP_ENV", "production")

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "Demo123456"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "邮箱或密码错误"


def test_production_rejects_existing_demo_account_token(client, db, monkeypatch):
    user = create_demo_user(db)
    token = create_access_token(user.id)
    monkeypatch.setattr(settings, "APP_ENV", "production")

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_development_allows_demo_account_login(client, db, monkeypatch):
    create_demo_user(db)
    monkeypatch.setattr(settings, "APP_ENV", "development")

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "Demo123456"},
    )

    assert response.status_code == 200


@pytest.mark.parametrize("subject", ["not-an-integer", "9223372036854775808"])
def test_rejects_invalid_token_subject_with_unauthorized(client, subject):
    token = create_access_token(subject)

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "认证凭据无效"
