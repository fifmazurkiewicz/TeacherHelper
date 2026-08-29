from teacher_helper.adapters.http.deps import _apply_admin_email_policy, _resolve_role_for_email
from teacher_helper.config import parse_admin_emails
from teacher_helper.infrastructure.db.models import UserORM, UserRole


def test_parse_admin_emails() -> None:
    assert parse_admin_emails("a@x.com, B@y.com") == frozenset({"a@x.com", "b@y.com"})


def test_resolve_role_for_email(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    from teacher_helper.config import get_settings

    get_settings.cache_clear()
    assert _resolve_role_for_email("admin@example.com") == UserRole.admin
    assert _resolve_role_for_email("teacher@example.com") == UserRole.teacher
    get_settings.cache_clear()


def test_apply_admin_email_policy_demotes_other_admins(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_EMAILS", "only@example.com")
    from teacher_helper.config import get_settings

    get_settings.cache_clear()
    user = UserORM(email="other@example.com", role=UserRole.admin)
    _apply_admin_email_policy(user, "other@example.com")
    assert user.role == UserRole.teacher

    user2 = UserORM(email="only@example.com", role=UserRole.teacher)
    _apply_admin_email_policy(user2, "only@example.com")
    assert user2.role == UserRole.admin
    get_settings.cache_clear()
