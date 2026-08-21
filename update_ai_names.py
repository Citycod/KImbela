from app_config import app
from extensions import db
from models import User

def update_names():
    surnames = {
        "Amara": "Okafor",
        "Tunde": "Balogun",
        "Ngozi": "Eze",
        "Emeka": "Obi"
    }

    with app.app_context():
        for name, surname in surnames.items():
            email = f"ai.{name.lower()}@kimbela.com"
            user = User.query.filter_by(email=email).first()
            if user:
                user.last_name = surname
                print(f"Updated {name} to last name: {surname}")
            else:
                print(f"User {name} not found.")
        
        db.session.commit()
        print("Done updating AI persona last names!")

if __name__ == "__main__":
    update_names()
