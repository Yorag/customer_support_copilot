from __future__ import annotations

from scripts import init_db


def test_init_db_accepts_database_url_without_postgres_parts(monkeypatch) -> None:
    settings = type(
        "Settings",
        (),
        {
            "database": type(
                "DatabaseSettings",
                (),
                {"url": "postgresql://postgres:postgres@localhost:5432/app"},
            )()
        },
    )()

    validate_calls: list[tuple[str, ...]] = []
    upgrade_calls: list[str] = []

    monkeypatch.setattr(init_db, "get_settings", lambda: settings)
    monkeypatch.setattr(
        init_db,
        "validate_required_settings",
        lambda names: validate_calls.append(tuple(names)),
    )
    monkeypatch.setattr(init_db, "Config", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        init_db.command,
        "upgrade",
        lambda _config, revision: upgrade_calls.append(revision),
    )

    init_db.main()

    assert validate_calls == []
    assert upgrade_calls == ["head"]


def test_init_db_validates_postgres_parts_when_database_url_missing(monkeypatch) -> None:
    settings = type(
        "Settings",
        (),
        {"database": type("DatabaseSettings", (), {"url": None})()},
    )()

    validate_calls: list[tuple[str, ...]] = []
    upgrade_calls: list[str] = []

    monkeypatch.setattr(init_db, "get_settings", lambda: settings)
    monkeypatch.setattr(
        init_db,
        "validate_required_settings",
        lambda names: validate_calls.append(tuple(names)),
    )
    monkeypatch.setattr(init_db, "Config", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        init_db.command,
        "upgrade",
        lambda _config, revision: upgrade_calls.append(revision),
    )

    init_db.main()

    assert validate_calls == [
        ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER")
    ]
    assert upgrade_calls == ["head"]
