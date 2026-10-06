"""Non-destructive migration for flight session boundary observations."""
from sqlalchemy import text
from app.database import engine
with engine.begin() as connection:
    connection.execute(text('ALTER TABLE aircraft_positions ADD COLUMN IF NOT EXISTS on_ground BOOLEAN'))
print('Position ground status column ready; historical values remain unknown.')
