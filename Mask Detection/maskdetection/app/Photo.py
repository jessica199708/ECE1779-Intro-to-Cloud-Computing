from app import db


class Photo(db.Model):
    __tablename__ = 'Photo'
    username = db.Column(db.String(100))
    photourl=db.Column(db.String(100), primary_key=True)
    imagetype = db.Column(db.Integer)