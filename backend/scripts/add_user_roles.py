"""Run from backend: python -m scripts.add_user_roles."""
from sqlalchemy import text
from app.database import engine

with engine.begin() as connection:
    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'viewer'"))
    connection.execute(text("""DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_role_check' AND conrelid = 'users'::regclass) THEN
            ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('viewer', 'analyst', 'admin'));
        END IF;
    END $$"""))
print('User roles schema updated.')
