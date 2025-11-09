from flask import (
    Flask,
    render_template,
    Response,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    Blueprint,
    make_response,
)
from flask_wtf.csrf import generate_csrf
import uuid
from io import BytesIO
# from sendgrid import SendGridAPIClient
# from sendgrid.helpers.mail import Mail, Content
from datetime import datetime, timedelta

from sqlalchemy.orm import joinedload


import bleach, os
from dotenv import load_dotenv
from extensions import mail
from flask_mail import Message

from sqlalchemy.orm import joinedload

from datetime import timedelta, datetime

from sqlalchemy.orm import joinedload
from io import BytesIO
from datetime import datetime
from weasyprint import HTML
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from extensions import db
from flask_bcrypt import bcrypt
from werkzeug.security import generate_password_hash, check_password_hash
import os, re
import cloudinary.uploader
from dotenv import load_dotenv
import pytz
import logging
from flask import flash, redirect, url_for, render_template, request
from flask_login import login_user, current_user
from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
    jsonify,
)
from flask_login import login_required, current_user
import logging
from sqlalchemy.sql import text
# from func import calculate_client_growth, get_audit_compliance
# import pdfkit, tempfile
from flask import send_file, render_template_string
from io import BytesIO
import shutil
from flask import render_template
import re
from cloudinary.uploader import upload


load_dotenv()
