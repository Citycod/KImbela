from runserver import app
from extensions import db
from models import Group, User, Post
import os

with app.app_context():
    print("Total Groups:", Group.query.count())
    print("Total Posts:", Post.query.count())
    print("Total Users:", User.query.count())
