# extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_mail import Mail

mail = Mail()

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
