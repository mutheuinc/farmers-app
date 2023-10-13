
import os, openai, io, base64, requests
from markupsafe import Markup
import secrets
import tempfile
from PIL import Image
from flask import jsonify, render_template, sessions, url_for, flash, redirect, request, session
from itsdangerous import BadSignature, Serializer, TimedSerializer, URLSafeTimedSerializer
from yaml import serialize_all 
from main import app, db, bcrypt, mail
from main.forms import RegistrationForm, LoginForm, FarmingInfoForm, UpdateAccountForm, RequestResetForm, ResetPasswordForm
from main.models import User
from flask_login import login_user, current_user, logout_user, login_required
from flask_mail import Message, Mail
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
from PIL import Image
from base64 import b64decode
from io import BytesIO
from dotenv import load_dotenv



@app.route("/")
@app.route("/home")
def home():
    return render_template('home.html')

@app.route("/about/")
def about():
    return render_template('about.html', title='about')


mail = Mail(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

@app.route("/registration", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_password)

        # Generate a confirmation token
        token = serializer.dumps(user.email, salt='email-confirm')

        # Send confirmation email
        confirmation_link = url_for('confirm_email', token=token, _external=True)
        message = Message('Confirm Your Email', recipients=[user.email], sender=app.config['MAIL_USERNAME'])
        message.body = f'Please click the link to confirm your email: {confirmation_link}'
        mail.send(message)

        db.session.add(user)
        db.session.commit()
        flash('Your account has been created. Please check your email to confirm your account.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Registration', form=form)


@app.route('/confirm_email/<token>')
def confirm_email(token):
    try:
        email = serializer.loads(token, salt='email-confirm', max_age=1800)  # 30 minutes expiration

        user = User.query.filter_by(email=email).first()
        if user:
            user.confirmed = True
            user.is_active = True
            db.session.commit()
            flash('Email confirmed. You can now log in.', 'success')
        else:
            flash('User not found.', 'danger')

    except BadSignature:
        flash('The confirmation link is invalid or has expired.', 'danger')

    return redirect(url_for('login'))


@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            if user.confirmed:
                login_user(user, remember=form.remember.data)
                next_page = request.args.get('next')
                return redirect(next_page) if next_page else redirect(url_for('home'))
            else:
                flash('Please confirm your email address to log in.', 'warning')
        else:
            flash('Login Unsuccessful. Please check email or password.', 'danger')
    return render_template('login.html', title='Login', form=form)


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('home'))


def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(app.root_path, 'static/profilepics', picture_fn)
    
    output_size = (125, 125)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    i.save(picture_path)

    return picture_fn


@app.route("/account", methods=['GET', 'POST'])
@login_required
def account():
    form= UpdateAccountForm()
    if form.validate_on_submit():
        if form.picture.data:
            picture_file = save_picture(form.picture.data)
            current_user.image_file = picture_file
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash('Account Updated!', 'success')
        return redirect(url_for('account'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
    image_file = url_for('static', filename='profilepics/' + current_user.image_file)
    return render_template('account.html', title='Account', image_file=image_file, form=form)


def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Password Reset Request',
                  sender='mylesadebayo@gmail.com',
                  recipients=[user.email])
    msg.body = f'''To reset your password, visit the following link:
{url_for('reset_token', token=token, _external=True)}

If you did not make this request then simply ignore this email and no changes will be made.
'''
    mail.send(msg)

 
@app.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('home_page'))
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        send_reset_email(user)
        flash('An email has been sent with instructions to reset your password.', 'info')
        return redirect(url_for('login'))
    return render_template('reset_request.html', title='Reset Password', form=form)


@app.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    user = User.verify_reset_token(token)
    if user is None:
        flash('That is an invalid or expired token', 'warning')
        return redirect(url_for('reset_request'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user.password = hashed_password
        db.session.commit()
        flash('Your password has been updated! You are now able to log in', 'success')
        return redirect(url_for('login'))
    return render_template('reset_token.html', title='Reset Password', form=form)


'''WEATHER AND SOIL APIs'''

@app.route('/dashboard')
def weatherinfo():
    response = requests.get('http://ip-api.com/json/')

    if response.status_code != 200:
        return 'Could not get location information.'

    location_data = response.json()
    session['location'] = location_data

    lat = location_data.get('lat')
    lon = location_data.get('lon')

#fetching weather data.
    weather_url = f'http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric'
    response = requests.get(weather_url)

    if response.status_code != 200:
        return 'Could not get weather information.'

    weather_data = response.json()
    #print(weather_data)  # Print out the data to understand the structure

    #fetching soil data.
    AMBEEDATA_API_KEY=os.getenv('AMBEEDATA_API_KEY')
    soil_url = f'https://api.ambeedata.com/latest/by-lat-lng?lat={lat}&lng={lon}'
    headers = {"x-api-key": AMBEEDATA_API_KEY}
    response = requests.get(soil_url, headers=headers)
    #print("Soil API Response: ", response.text)  # Add this line to print the response.

    if response.status_code != 200:
        return 'Could not get soil information.'
    else:
        soil_data = response.json()
        #print(soil_data )

    return render_template('weather.html', weather_data=weather_data, soil_data=soil_data)


'''
WORKING WITH API
'''
load_dotenv()
app.secret_key = os.getenv('APPSECRET_KEY')
OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY')
OPEN_API_KEY = os.getenv('OPENAI_KEY')
openai.api_key = OPEN_API_KEY
hf_api_key = os.getenv('HF_API_KEY')

'''
1. OPENAI API
'''
base_url = "https://api.openai.com/v1/"


'''Image Model DallE'''
def dalle_image(prompt, size):

    data = {
        "prompt": prompt,
        "size": size,
        # Fill in this line, (prompt)
        # Fill in this line, (size)
        'response_format': 'b64_json',
    }

    # download and transform the image
    response = requests.post(
        base_url + '/images/generations',
        headers={'Authorization': f'Bearer {OPEN_API_KEY}'},
        json=data
    )
    b64_image_data = response.json().get('data', [])[0].get('b64_json', '')

    decoded_image = base64.b64decode(b64_image_data)
    image = Image.open(BytesIO(decoded_image))

    return image

'''Image Model with Stable Diffusion'''
def stablediffusion_image(hf_api_key, text):
    url = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2"
    headers = {"Authorization": f"Bearer {hf_api_key}"}

    data = {"inputs": text}

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()

        # Check if the response contains image data
        if 'image' in response.headers.get('Content-Type', '').lower():
            return response.content
    except Exception as e:
        print("Error occurred:", e)

    return None

'''ChatCompletion Model'''
chat_log = []
@app.route('/farminginfo', methods=['GET', 'POST'])
def farminginfo():
    
    response = requests.get('http://ip-api.com/json/')

    if response.status_code != 200:
        return 'Could not get location information.'

    location_data = response.json()
    session['location'] = location_data

    lat = location_data.get('lat')
    lon = location_data.get('lon')

#fetching weather data.
    weather_url = f'http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric'
    response = requests.get(weather_url)

    if response.status_code != 200:
        return 'Could not get weather information.'

    weather_data = response.json()
    #print(weather_data)  # Print out the data to understand the structure

  #fetching soil data.
    AMBEEDATA_API_KEY=os.getenv('AMBEEDATA_API_KEY')
    soil_url = f'https://api.ambeedata.com/latest/by-lat-lng?lat={lat}&lng={lon}'
    headers = {"x-api-key": AMBEEDATA_API_KEY}
    response = requests.get(soil_url, headers=headers)
    #print("Soil API Response: ", response.text)  # Add this line to print the response.

    if response.status_code != 200:
        return 'Could not get soil information.'
    else:
        soil_data = response.json()
        #print(soil_data )
    
    form = FarmingInfoForm()

    if request.method == 'POST' and form.validate_on_submit():
        # Create a message for the GPT-4 model
        user_message = f"based on this weather data: {weather_data} and this soil information:{soil_data}, suggest four crops to plant that will grow well with such weather conditions and soil information."
        #user_message = f"name one crop"
        # Append the user's message to the chat log
        chat_log.append({"role": "user", "content": user_message})
        

        # Send the message to the GPT-4 model
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=chat_log
        )

        # Extract the assistant's response
        assistant_response = response['choices'][0]['message']['content']

        # Append the assistant's response to the chat log
        chat_log.append({"role": "assistant", "content": assistant_response})
        #chat_log.append(assistant_response)
        
        first_crop = f"give only the names of the first four crop suggestion, names only: {assistant_response}"
        response2 = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=chat_log + [{"role": "user", "content": first_crop}]
        )
        crops = response2['choices'][0]['message']['content']
        chat_log.append({"role": "assistant", "content": crops})
        #chat_log.append(firstt_crop)
        
        
        image_data = None
        prompt = f"generate four seperate different realistic seed images of each of the crops in: {crops}"
        size = "512x512"
        image = dalle_image(prompt, size)
        
        # Convert the image to bytes and encode it in base64
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        image_data = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # Render the 'gpt.html' template with the form and response
        return render_template('farminginfo.html', title='farminginfo', form=form, assistant_response=assistant_response,firstt_crop=crops, image_data=image_data)

    # Render the 'gpt.html' template with the form when the page is initially loaded
    return render_template('farminginfo.html', title='farminginfo', form=form)

'''Pest Control Suggestion Model'''

@app.route('/get_pest_control', methods=['POST'])
def get_pest_control_advice():
    data = request.get_json()
    assistant_response = data.get('assistantResponse')

    # Initialize chat log with the assistant's response and a question about pests
    chat_log = [{"role": "user", "content": assistant_response},
                {"role": "assistant", "content": "for each one of the crops, what pests affect them and suggest two ways to protect ech of those crops?"}]

    try:
        # Send the chat log to the GPT-3.5-turbo model
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=chat_log,
        )

        # Extract the assistant's response from the model's output
        assistant_response = response['choices'][0]['message']['content']

        return jsonify({"pestControlAdvice": assistant_response})

    except Exception as e:
        # Handle errors appropriately
        return jsonify({"error": str(e)})


'''TESTING THE APIs'''
# Route for the home page
@app.route('/openai', methods=['GET', 'POST'])
def dalle():
    image_data = None
    if request.method == 'POST':
        prompt = request.form.get('prompt')
        size = request.form.get('size')
        image = dalle_image(prompt, size)
        
        # Convert the image to bytes and encode it in base64
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        image_data = base64.b64encode(buffered.getvalue()).decode('utf-8')

    return render_template('openai.html', image_data=image_data) 

@app.route('/huggingface', methods=['GET', 'POST'])
def huggingface():
    image_data = None
    if request.method == 'POST':
        text = request.form.get('text')
        image_bytes = stablediffusion_image(hf_api_key, text)

        if image_bytes:
            # Convert the image bytes to base64
            image_data = base64.b64encode(image_bytes).decode('utf-8')

    return render_template('huggingface.html', image_data=Markup(image_data))


