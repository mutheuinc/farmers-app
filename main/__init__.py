from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_mail import Mail
from flask_login import LoginManager
from itsdangerous import TimedSerializer, URLSafeTimedSerializer 

app = Flask(__name__)
app.config['SECRET_KEY'] = '5791628bb0b13ce0c676dfde280ba245'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:faraja@localhost/agrisense'
app.config.from_pyfile('../config.cfg')
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'
app.config['MAIL_SERVER'] = 'smtp.googlemail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = 'mylesadebayo@gmail.com'
app.config['MAIL_PASSWORD'] = 'nmqrtdbmbfijlthn'

mail = Mail(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

from main import routes