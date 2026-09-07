from app_config import app
from extensions import db
from models import AIPersona, User


DISPLAY_NAME_UPDATES = {
    # Stable account emails are retained so this updates rather than creates.
    "ai.amara@kimbela.com": ("Emily", "Carter"),
    "ai.tunde@kimbela.com": ("Daniel", "Brooks"),
}


def update_names(app_instance=None):
    target_app = app_instance or app
    with target_app.app_context():
        for email, (first_name, last_name) in DISPLAY_NAME_UPDATES.items():
            user = User.query.filter_by(email=email).first()
            if user:
                user.first_name = first_name
                user.last_name = last_name
                persona = AIPersona.query.filter_by(user_id=user.id).first()
                if persona:
                    persona.name = f"{first_name} {last_name}"
                print(f"Updated {email} display name to {first_name} {last_name}")
            else:
                print(f"User {email} not found.")
        
        db.session.commit()
        print("Done updating AI persona display names!")


if __name__ == "__main__":
    update_names()
