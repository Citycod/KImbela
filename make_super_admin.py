import sys

from runserver import app
from extensions import db
from models import User


def main():
    if len(sys.argv) != 2:
        print("Usage: python make_super_admin.py <email>")
        sys.exit(1)

    email = sys.argv[1].strip().lower()
    if not email:
        print("Email is required")
        sys.exit(1)

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if not user:
            print(f"User not found: {email}")
            sys.exit(1)

        user.is_super_admin = True
        user.is_admin = True
        user.is_active = True
        user.admin_role = "super_admin"
        user.admin_permissions = None
        db.session.commit()

    print(f"Super admin set for {email}")


if __name__ == "__main__":
    main()
