#!/bin/bash
export FLASK_APP=runserver.py
export FLASK_ENV=development
export FLASK_DEBUG=1
source venv/bin/activate
python runserver.py
