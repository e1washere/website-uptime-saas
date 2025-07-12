"""
Website Uptime Monitoring SaaS Application
A Flask-based service for monitoring website uptime with email notifications and Stripe payments
"""

import os
import logging
from datetime import datetime, timedelta
from functools import wraps
import requests
from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import stripe
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///uptime_monitor.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Email configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')

# Stripe configuration
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
STRIPE_PRICE_ID = os.getenv('STRIPE_PRICE_ID')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
mail = Mail(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    trial_ends_at = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(days=7))
    stripe_customer_id = db.Column(db.String(100))
    subscription_status = db.Column(db.String(50), default='trialing')
    subscription_id = db.Column(db.String(100))
    websites = db.relationship('Website', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_active_subscriber(self):
        """Check if user has active subscription or is in trial period"""
        if self.subscription_status == 'active':
            return True
        if self.subscription_status == 'trialing' and datetime.utcnow() < self.trial_ends_at:
            return True
        return False

class Website(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(20), default='UNKNOWN')  # UP, DOWN, UNKNOWN
    last_checked = db.Column(db.DateTime)
    last_status_change = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def check_status(self):
        """Check if the website is up or down"""
        try:
            response = requests.get(self.url, timeout=10)
            new_status = 'UP' if response.status_code < 400 else 'DOWN'
        except:
            new_status = 'DOWN'
        
        old_status = self.status
        self.status = new_status
        self.last_checked = datetime.utcnow()
        
        # If status changed, update last_status_change and send notification
        if old_status != new_status and old_status != 'UNKNOWN':
            self.last_status_change = datetime.utcnow()
            if new_status == 'DOWN':
                send_down_notification(self)
        
        db.session.commit()
        return new_status

# Login manager loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Decorator to require active subscription
def subscription_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if not current_user.is_active_subscriber():
            flash('Please subscribe to continue using the service.', 'warning')
            return redirect(url_for('pricing'))
        return f(*args, **kwargs)
    return decorated_function

# Email notification function
def send_down_notification(website):
    """Send email notification when website goes down"""
    try:
        user = website.user
        msg = Message(
            f'Alert: {website.url} is DOWN',
            recipients=[user.email]
        )
        msg.body = f"""
        Hello,

        Your monitored website {website.url} is currently DOWN.
        
        Last checked: {website.last_checked.strftime('%Y-%m-%d %H:%M:%S UTC')}
        
        We'll continue monitoring and notify you when it's back up.

        Best regards,
        Uptime Monitor Team
        """
        mail.send(msg)
        logger.info(f"Sent down notification for {website.url} to {user.email}")
    except Exception as e:
        logger.error(f"Failed to send email notification: {str(e)}")

# Background job to check websites
def check_all_websites():
    """Check all websites for all active users"""
    with app.app_context():
        try:
            # Get all websites for active subscribers
            active_users = User.query.filter(
                (User.subscription_status == 'active') | 
                ((User.subscription_status == 'trialing') & (User.trial_ends_at > datetime.utcnow()))
            ).all()
            
            for user in active_users:
                for website in user.websites:
                    website.check_status()
                    logger.info(f"Checked {website.url}: {website.status}")
        except Exception as e:
            logger.error(f"Error in check_all_websites: {str(e)}")

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(
    func=check_all_websites,
    trigger=IntervalTrigger(minutes=5),
    id='check_websites',
    name='Check all websites',
    replace_existing=True
)
scheduler.start()

# Routes
@app.route('/')
def index():
    """Landing page"""
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Validate input
        if not email or not password:
            flash('Please provide both email and password.', 'danger')
            return redirect(url_for('register'))
        
        # Check if user exists
        if User.query.filter_by(email=email).first():
            flash('Email already registered. Please login.', 'warning')
            return redirect(url_for('login'))
        
        # Create new user
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        flash('Registration successful! You have a 7-day free trial.', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('login.html', mode='register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
    
    return render_template('login.html', mode='login')

@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
@subscription_required
def dashboard():
    """User dashboard"""
    websites = Website.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', 
                         websites=websites, 
                         max_websites=3,
                         is_active=current_user.is_active_subscriber())

@app.route('/add_website', methods=['POST'])
@login_required
@subscription_required
def add_website():
    """Add a new website to monitor"""
    url = request.form.get('url')
    
    if not url:
        flash('Please provide a URL.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Ensure URL has protocol
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Check website limit
    website_count = Website.query.filter_by(user_id=current_user.id).count()
    if website_count >= 3:
        flash('You have reached the maximum of 3 websites. Please remove one to add another.', 'warning')
        return redirect(url_for('dashboard'))
    
    # Add website
    website = Website(user_id=current_user.id, url=url)
    db.session.add(website)
    db.session.commit()
    
    # Check status immediately
    website.check_status()
    
    flash('Website added successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/remove_website/<int:website_id>')
@login_required
def remove_website(website_id):
    """Remove a website from monitoring"""
    website = Website.query.filter_by(id=website_id, user_id=current_user.id).first()
    
    if website:
        db.session.delete(website)
        db.session.commit()
        flash('Website removed successfully!', 'success')
    else:
        flash('Website not found.', 'danger')
    
    return redirect(url_for('dashboard'))

@app.route('/pricing')
def pricing():
    """Pricing page"""
    return render_template('pricing.html', 
                         stripe_publishable_key=STRIPE_PUBLISHABLE_KEY,
                         price_id=STRIPE_PRICE_ID)

@app.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    """Create Stripe checkout session"""
    try:
        # Create or retrieve Stripe customer
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_user.email
            )
            current_user.stripe_customer_id = customer.id
            db.session.commit()
        
        # Create checkout session
        checkout_session = stripe.checkout.Session.create(
            customer=current_user.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': STRIPE_PRICE_ID,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=url_for('subscription_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('pricing', _external=True),
        )
        
        return redirect(checkout_session.url, code=303)
    
    except Exception as e:
        logger.error(f"Stripe error: {str(e)}")
        flash('An error occurred. Please try again.', 'danger')
        return redirect(url_for('pricing'))

@app.route('/subscription-success')
@login_required
def subscription_success():
    """Handle successful subscription"""
    session_id = request.args.get('session_id')
    
    if session_id:
        try:
            # Retrieve the session
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            
            # Update user subscription
            current_user.subscription_id = checkout_session.subscription
            current_user.subscription_status = 'active'
            db.session.commit()
            
            flash('Subscription successful! Thank you for subscribing.', 'success')
        except Exception as e:
            logger.error(f"Error processing subscription: {str(e)}")
            flash('There was an issue processing your subscription. Please contact support.', 'danger')
    
    return redirect(url_for('dashboard'))

@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhooks"""
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        # Invalid payload
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        return 'Invalid signature', 400
    
    # Handle the event
    if event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        user = User.query.filter_by(subscription_id=subscription['id']).first()
        if user:
            user.subscription_status = 'cancelled'
            db.session.commit()
    
    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        user = User.query.filter_by(subscription_id=subscription['id']).first()
        if user:
            user.subscription_status = subscription['status']
            db.session.commit()
    
    return 'Success', 200

# Create tables
with app.app_context():
    db.create_all()

# Shutdown scheduler on app exit
import atexit
atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    app.run(debug=True) 