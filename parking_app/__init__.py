from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import DevelopmentConfig
import os
import pytz

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__, 
                instance_relative_config=True,
                static_folder='../static',
                template_folder='../templates')
    app.config.from_object(DevelopmentConfig)
    
    # Ensure the instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(app.instance_path, "parking.db")}'

    # Template filters
    @app.template_filter('ist_time')
    def ist_time_filter(dt):
        """Convert datetime to IST and format it"""
        if dt is None:
            return 'N/A'
        
        # If the datetime is naive (no timezone), assume it's UTC
        if dt.tzinfo is None:
            dt = pytz.timezone('Asia/Kolkata').localize(dt)
        else:
            # If it's already timezone-aware, convert it to IST
            ist = pytz.timezone('Asia/Kolkata')
            dt = dt.astimezone(ist)
        
        return dt.strftime('%Y-%m-%d %H:%M:%S IST')

    @app.template_filter('format_currency')
    def format_currency_filter(amount):
        """Format currency in Indian Rupees"""
        if amount is None:
            return 'N/A'
        return f"₹{amount:.2f}"

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'
    login_manager.login_message_category = 'info'

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from .controllers import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .api import api as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api')

    with app.app_context():
        db.create_all()
        # Create admin user if it doesn't exist
        if not User.query.filter_by(email="admin@gmakil.com").first():
            admin = User(username='admin', email='admin@gmakil.com', role='admin')
            admin.set_password('admin')
            db.session.add(admin)
            db.session.commit()
            print("Admin user created successfully: username='admin', email='admin@gmakil.com', password='admin'")

    return app
