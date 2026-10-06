from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker
import os 
from pathlib import Path
from dotenv import load_dotenv
from .models import Base

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]


engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True,
    echo=False, 
    pool_size=5,
    max_overflow=10
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)     

def get_db():
    #FastAPI dependency for database sessions
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    #Creates all tables in database if they do not exist
    try:
        Base.metadata.create_all(bind=engine)
        print("Database tables created/verified")
        return True
    except Exception as e:
        print(f"Error creating tables: {e}")
        return False

def test_connection():
    """Test database connection and show version info"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"PostgreSQL: {version[:60]}...")
            
            try:
                result = conn.execute(text("SELECT PostGIS_version()"))
                postgis = result.fetchone()[0]
                print(f"PostGIS: {postgis}")
            except:
                print("PostGIS not detected")
                
            return True
    except Exception as e:
        print(f"Connection failed: {e}")
        return False

if __name__ == "__main__":
    print("="*60)
    print("Testing Database Connection")
    print("="*60)
    if test_connection():
        print("\n" + "="*60)
        print("Initializing Database Tables")
        print("="*60)
        init_db()

