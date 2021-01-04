from app import app, db
from app.User import User
from app.Photo import Photo

@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'User': User, 'Photo': Photo}

if __name__=="__main__":
  app.run(port=5001,debug=True)