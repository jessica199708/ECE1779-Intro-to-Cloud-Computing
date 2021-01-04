import os
import urllib.request
import requests
from werkzeug.utils import secure_filename
from flask import render_template, flash, redirect, url_for, abort, send_from_directory, jsonify
from app import app
from app.forms import LoginForm
from flask_login import current_user, login_user
from app.User import User
from app.Photo import Photo
from flask_login import logout_user
from flask_login import login_required
from flask import request
from werkzeug.urls import url_parse
from app import db
from app.forms import RegistrationForm, DeleteAccountForm, URLUploadPhotoForm
import uuid
from app.pytorch_infer import inference
from app.forms import ResetPasswordRequestForm
from app.email import send_password_reset_email
from app.forms import ResetPasswordForm
import boto3

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

@app.route('/index')
@login_required
def index():
    files = []
    photos0 = []
    photos1 = []
    photos2 = []
    photos3 = []
    photos_object = Photo.query.filter_by(username=current_user.get_username()).all()
    for photo in photos_object:
        files.append(photo.photourl)
        if photo.imagetype == 0:
            photos0.append(photo.photourl)
        elif photo.imagetype == 1:
            photos1.append(photo.photourl)
        elif photo.imagetype == 2:
            photos2.append(photo.photourl)
        else:
            photos3.append(photo.photourl)

    return render_template('index.html', files=files, photos0=photos0, photos1=photos1, photos2=photos2, photos3=photos3)



@app.route('/index', methods=['POST'])
def upload():
    s3 = boto3.client('s3')
    uploaded_file = request.files['file']
    filename = secure_filename(uploaded_file.filename)
    filename = str(uuid.uuid4()) + filename
    if filename != '':
        file_ext = os.path.splitext(filename)[1]
        if file_ext not in app.config['UPLOAD_EXTENSIONS']:
            flash('Wrong format!')
            return redirect(url_for('index'))
        uploaded_file.save(os.path.join('app/static/image', filename))
        s3.upload_file(os.path.join(PROJECT_ROOT, 'static/image/'+filename), app.config['BUCKET_NAME'], 'image/{}'.format(filename))
        flash('Successfully Submit!')
    else:
        flash('This field can not be blank!')

    num_face = 0
    num_mask = 0
    num_unmask = 0
    image_type = 0
    output_info = inference(os.path.join(PROJECT_ROOT, 'static/image/'+filename), os.path.join(PROJECT_ROOT, 'static/output/'+filename), filename,
                            show_result=False, target_shape=(360, 360))
    num_face = len(output_info)
    for i in range(num_face):
        if output_info[i][0] == 0:
            num_mask += 1
        else:
            num_unmask += 1
    if num_face == 0:
        image_type = 0  # no face
    elif num_face == num_mask:
        image_type = 1  # all masked
    elif num_face == num_unmask:
        image_type = 2  # all unmasked
    else:
        image_type = 3  # some masked

    u = Photo(username=current_user.username, photourl=filename, imagetype=image_type)
    db.session.add(u)
    db.session.commit()
    flash('There are {} faces been detected, {} mask faces been detected, {} unmasked faces been detected.'.format(num_face,num_mask,num_unmask))

    return redirect(url_for('index'))



@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password')
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    return render_template('login.html', title='Sign In', form=form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('You have created a new user account successfully!')
        return redirect(url_for('index'))
    return render_template('register.html', title='Register', form=form)


@app.route('/delete_account', methods=['GET', 'POST'])
def delete_account():
    form = DeleteAccountForm()
    if form.validate_on_submit():
        User.query.filter_by(username = form.username.data, email = form.email.data).delete()
        db.session.commit()
        flash('You have deleted an account successfully!')
        return redirect(url_for('index'))
    return render_template('delete_account.html', title='Delete_Account', form=form)


@app.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_password_reset_email(user)
        flash('Check your email for the instructions to reset your password')
        return redirect(url_for('login'))
    return render_template('reset_password_request.html',
                           title='Reset Password', form=form)



@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    user = User.verify_reset_password_token(token)
    if not user:
        return redirect(url_for('index'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been reset.')
        return redirect(url_for('login'))
    return render_template('reset_password.html', form=form)


# api register routes which used for automatic testing
# it takes username and password and validate them
# it will check the username and passoword and ensure they both valid first
@app.route('/api/register', methods=['GET', 'POST'])
def APIregister():
    user = User.query.filter_by(username=request.form.get('username')).first()
    if user:
        response = jsonify({"Success": False})
        response.status_code = 400
        return response
    else:
        user = User(username=request.form.get('username'), email=request.form.get('email'))
        user.set_password(request.form.get('password'))
        db.session.add(user)
        db.session.commit()
        responseString = {"Success": True}
        response = jsonify(responseString)
        response.status_code = 200
        return response


# api upload routes which used for automatic testing
# it will valid the username and password first
# it will read and past all the valid files
# save and create the detected version

@app.route('/api/upload', methods=['GET', 'POST']) ## upload testing
def APIupload():
    username = request.form.get("username")
    password = request.form.get("password")
    filelist = request.files.getlist('file')
    user = User.query.filter_by(username = username).first()
    if user is None or not user.check_password(password):
        response = jsonify({"Success": False})
        response.status_code = 400
        return response
    else:
        for uploaded_file in filelist:
            filename = secure_filename(uploaded_file.filename)
            filename = str(uuid.uuid4()) + filename
            if filename != '':
                file_ext = os.path.splitext(filename)[1]
                if file_ext not in app.config['UPLOAD_EXTENSIONS']:
                    response = jsonify({"error": {"code": 400, "message": "Error message!"}})
                    response.status_code = 400
                    return response
                else:
                    uploaded_file.save(os.path.join('app/static/image', filename))
            else:
                response = jsonify({"error": {"code": 400, "message": "Error message!"}})
                response.status_code = 400
                return response

            num_face = 0
            num_mask = 0
            num_unmask = 0
            image_type = 0
            output_info = inference(os.path.join('app/static/image', filename),
                                    os.path.join('app/static/output', filename),
                                    show_result=False, target_shape=(360, 360))
            num_face = len(output_info)
            for i in range(num_face):
                if output_info[i][0] == 0:
                    num_mask += 1
                else:
                    num_unmask += 1
            if num_face == 0:
                image_type = 0  # no face
            elif num_face == num_mask:
                image_type = 1  # all masked
            elif num_face == num_unmask:
                image_type = 2  # all unmasked
            else:
                image_type = 3  # some masked

            u = Photo(username = username, photourl=filename, imagetype=image_type)
            db.session.add(u)
            db.session.commit()
        response = jsonify({"success": True, "payload": {"num_faces": num_face,"num_masked": num_mask,"num_unmasked": num_unmask}})
        response.status_code = 200
        return response

@app.route('/urlupload', methods=['GET','POST'])
def urlupload():
    form = URLUploadPhotoForm()
    if form.validate_on_submit():
        photourl = form.photoURL.data
        print(photourl)
        filename = photourl.split('/')[-1]
        filename = secure_filename(filename)
        filename = str(uuid.uuid4()) + filename
        if filename != '':
            file_ext = os.path.splitext(filename)[1]
            if file_ext in app.config['UPLOAD_EXTENSIONS']:
                urllib.request.urlretrieve(photourl, os.path.join('app/static/image', filename))
                flash('Successfully Submit!')

        num_face = 0
        num_mask = 0
        num_unmask = 0
        image_type = 0
        output_info = inference(os.path.join('app/static/image', filename), os.path.join('app/static/output', filename),
                                show_result=False, target_shape=(360, 360))
        num_face = len(output_info)
        for i in range(num_face):
            if output_info[i][0] == 0:
                num_mask += 1
            else:
                num_unmask += 1
        if num_face == 0:
            image_type = 0  # no face
        elif num_face == num_mask:
            image_type = 1  # all masked
        elif num_face == num_unmask:
            image_type = 2  # all unmasked
        else:
            image_type = 3  # some masked

        u = Photo(username=current_user.username, photourl=filename, imagetype=image_type)
        db.session.add(u)
        db.session.commit()
        flash('There are {} faces been detected, {} mask faces been detected, {} unmasked faces been detected.'.format(num_face, num_mask, num_unmask))
        return redirect(url_for('index'))
    return render_template('urlupload.html', form=form)






