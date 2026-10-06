"""Local administrative tool: python -m scripts.set_user_role USERNAME ROLE."""
import argparse
from app.database import SessionLocal
from app.models import User

parser = argparse.ArgumentParser(description='Assign a role to an existing user')
parser.add_argument('username')
parser.add_argument('role', choices=['viewer', 'analyst', 'admin'])
args = parser.parse_args()
with SessionLocal() as db:
    user = db.query(User).filter(User.username == args.username).first()
    if user is None:
        parser.error('User not found; register the account first')
    user.role = args.role
    db.commit()
print('User role updated.')
