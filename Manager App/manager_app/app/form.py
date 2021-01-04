from app import db

class autoscalingForm(db.Model):
    __tablename__ = 'AutoScale'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime)
    threshold_max = db.Column(db.Float)
    threshold_min = db.Column(db.Float)
    ratio_expand = db.Column(db.Float)
    ratio_shrink = db.Column(db.Float)

class Photo(db.Model):
    __tablename__ = 'Photo'
    username = db.Column(db.String(100))
    photourl=db.Column(db.String(100), primary_key=True)
    imagetype = db.Column(db.Integer)

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))

