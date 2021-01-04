from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import time
from app.config import Config
app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)
instance_start_time = time.time()
from app import routes, form, config, auto_scaling, manager
