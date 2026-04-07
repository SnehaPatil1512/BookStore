from sqlalchemy import create_engine, MetaData, text

# =========================
# OLD DATABASE (SQLite)
# =========================
sqlite_engine = create_engine("sqlite:///./test.db")

# =========================
# NEW DATABASE (PostgreSQL)
# =========================
postgres_engine = create_engine(
    "postgresql://bookstoredb_s2xw_user:rICJrRkEFF9WjHk9eDgonQwVIjJDia2j@dpg-d7aaimuuk2gs73bocg30-a.oregon-postgres.render.com/bookstoredb_s2xw"
)

meta = MetaData()


# =========================
# RESET POSTGRES SCHEMA
# WARNING: THIS DELETES EVERYTHING
# =========================
def reset_postgres_schema():
    with postgres_engine.connect() as conn:
        print("Dropping public schema...")
        conn.execute(text("DROP SCHEMA public CASCADE"))

        print("Recreating public schema...")
        conn.execute(text("CREATE SCHEMA public"))

        conn.commit()
        print("Schema reset completed.")


# =========================
# REFLECT SQLITE SCHEMA
# =========================
def reflect_sqlite_schema():
    print("Reflecting SQLite schema...")
    meta.reflect(bind=sqlite_engine)
    print("Reflection completed.")


# =========================
# CREATE TABLES IN POSTGRES
# =========================
def create_tables_postgres():
    print("Creating tables in PostgreSQL...")
    meta.create_all(postgres_engine)
    print("Tables created successfully.")


# =========================
# COPY DATA FROM SQLITE → POSTGRES
# =========================
def copy_data():
    print("Starting data migration...")

    with sqlite_engine.connect() as old_conn:
        with postgres_engine.connect() as new_conn:

            for table in meta.sorted_tables:
                print(f"Migrating table: {table.name}")

                rows = old_conn.execute(table.select()).fetchall()

                if rows:
                    new_conn.execute(
                        table.insert(),
                        [dict(row._mapping) for row in rows]
                    )

            new_conn.commit()

    print("Data migration completed successfully!")


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    try:
        reset_postgres_schema()
        reflect_sqlite_schema()
        create_tables_postgres()
        copy_data()

        print("🎉 FULL MIGRATION SUCCESSFUL!")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        raise