from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings
from .constants import REVIEW_CATEGORY_NAME


LEGACY_USER_EMAIL = "__legacy__@scanny.local"

settings.database_path.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(
    f"sqlite:///{settings.database_path}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def init_db() -> None:
    # Import every model before create_all so new auth tables are registered.
    from .models import AuthSession, Category, Document, User  # noqa: F401

    Base.metadata.create_all(engine)
    category_columns = {column["name"] for column in inspect(engine).get_columns("categories")}
    document_columns = {column["name"] for column in inspect(engine).get_columns("documents")}

    connection = engine.connect()
    try:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()

        legacy_user_id: int | None = None
        if "user_id" not in category_columns or "user_id" not in document_columns:
            existing_data = connection.execute(
                text(
                    "SELECT (SELECT COUNT(*) FROM categories) + "
                    "(SELECT COUNT(*) FROM documents)"
                )
            ).scalar_one()
            if existing_data:
                legacy_user_id = connection.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": LEGACY_USER_EMAIL},
                ).scalar_one_or_none()
                if legacy_user_id is None:
                    result = connection.execute(
                        text(
                            "INSERT INTO users (email, password_hash, created_at) "
                            "VALUES (:email, :password_hash, CURRENT_TIMESTAMP)"
                        ),
                        {"email": LEGACY_USER_EMAIL, "password_hash": "!legacy-account"},
                    )
                    legacy_user_id = int(result.lastrowid)
                connection.commit()

        if "user_id" not in category_columns:
            if legacy_user_id is None:
                raise RuntimeError("Cannot migrate categories without an owner")
            connection.exec_driver_sql(
                """
                CREATE TABLE categories_new (
                    id INTEGER NOT NULL PRIMARY KEY,
                    name VARCHAR(80) NOT NULL,
                    created_at DATETIME NOT NULL,
                    is_system BOOLEAN NOT NULL,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    CONSTRAINT uq_categories_user_name UNIQUE (user_id, name)
                )
                """
            )
            connection.execute(
                text(
                    "INSERT INTO categories_new (id, name, created_at, is_system, user_id) "
                    "SELECT id, name, created_at, is_system, :user_id FROM categories"
                ),
                {"user_id": legacy_user_id},
            )
            connection.exec_driver_sql("DROP TABLE categories")
            connection.exec_driver_sql("ALTER TABLE categories_new RENAME TO categories")
            connection.exec_driver_sql("CREATE INDEX ix_categories_user_id ON categories (user_id)")

        if "user_id" not in document_columns:
            if legacy_user_id is None:
                raise RuntimeError("Cannot migrate documents without an owner")
            connection.exec_driver_sql("ALTER TABLE documents ADD COLUMN user_id INTEGER REFERENCES users(id)")
            connection.execute(
                text(
                    "UPDATE documents SET user_id = COALESCE("
                    "(SELECT user_id FROM categories WHERE categories.id = documents.category_id), :user_id)"
                ),
                {"user_id": legacy_user_id},
            )
            connection.exec_driver_sql("CREATE INDEX ix_documents_user_id ON documents (user_id)")

        if "scan_mode" not in document_columns:
            connection.exec_driver_sql(
                "ALTER TABLE documents ADD COLUMN scan_mode VARCHAR(20) NOT NULL DEFAULT 'color'"
            )
        if "scan_revision" not in document_columns:
            connection.exec_driver_sql(
                "ALTER TABLE documents ADD COLUMN scan_revision INTEGER NOT NULL DEFAULT 0"
            )
        if "embedding_json" not in document_columns:
            connection.exec_driver_sql("ALTER TABLE documents ADD COLUMN embedding_json JSON")
        if "embedding_model" not in document_columns:
            connection.exec_driver_sql("ALTER TABLE documents ADD COLUMN embedding_model VARCHAR(100)")
        if "embedding_updated_at" not in document_columns:
            connection.exec_driver_sql("ALTER TABLE documents ADD COLUMN embedding_updated_at DATETIME")

        if legacy_user_id is not None:
            review_category_id = connection.execute(
                text(
                    "SELECT id FROM categories WHERE user_id = :user_id "
                    "AND is_system = 1 LIMIT 1"
                ),
                {"user_id": legacy_user_id},
            ).scalar_one_or_none()
            if review_category_id is None:
                connection.execute(
                    text(
                        "INSERT INTO categories (name, created_at, is_system, user_id) "
                        "VALUES (:name, CURRENT_TIMESTAMP, 1, :user_id)"
                    ),
                    {"name": REVIEW_CATEGORY_NAME, "user_id": legacy_user_id},
                )
            else:
                connection.execute(
                    text("UPDATE categories SET is_system = 1 WHERE id = :id"),
                    {"id": review_category_id},
                )

        # Preserve the stable system-category identity while migrating its old
        # user-facing label. A conflicting user-created folder is left intact;
        # API serializers still expose the canonical system label.
        system_categories = connection.execute(
            text("SELECT id, user_id FROM categories WHERE is_system = 1")
        ).mappings().all()
        for category in system_categories:
            conflict = connection.execute(
                text(
                    "SELECT 1 FROM categories WHERE user_id = :user_id AND id != :id "
                    "AND lower(name) = lower(:name) LIMIT 1"
                ),
                {
                    "user_id": category["user_id"],
                    "id": category["id"],
                    "name": REVIEW_CATEGORY_NAME,
                },
            ).scalar_one_or_none()
            if conflict is None:
                connection.execute(
                    text("UPDATE categories SET name = :name WHERE id = :id"),
                    {"name": REVIEW_CATEGORY_NAME, "id": category["id"]},
                )
        connection.commit()
    finally:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.close()
