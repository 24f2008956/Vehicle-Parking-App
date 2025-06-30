import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pytz
from config import DevelopmentConfig

# Initialize Flask app
app = Flask(__name__)

# Create instance directory if it doesn't exist
instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
os.makedirs(instance_path, exist_ok=True)

# App configuration
app.config.from_object(DevelopmentConfig)

# Initialize extensions
try:
    db = SQLAlchemy(app)
except Exception as e:
    print(f"Error initializing database: {e}")
    raise

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

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

# User model
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")
    bookings = db.relationship('Booking', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == 'admin'

# Parking lot model
class Parking_lot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    address = db.Column(db.String(200), nullable=False, unique=True)
    pincode = db.Column(db.String(10), nullable=False)
    price_per_hour = db.Column(db.Float, nullable=False, default=60.0)  # Default to Rs. 60 per hour
    max_no_spots = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Kolkata')))
    spots = db.relationship('Parking_spot', backref='lot', lazy=True, cascade="all, delete-orphan")

# Parking spot model
class Parking_spot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    parking_lot_id = db.Column(db.Integer, db.ForeignKey('parking_lot.id'), nullable=False)
    spot_number = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(1), default='A')  # 'A' for Available, 'O' for Occupied
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Track who parked
    bookings = db.relationship('Booking', backref='parking_spot', lazy=True, cascade="all, delete-orphan")

# Booking model
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    parking_lot_id = db.Column(db.Integer, db.ForeignKey('parking_lot.id'), nullable=False)
    parking_spot_id = db.Column(db.Integer, db.ForeignKey('parking_spot.id'), nullable=False)
    vehicle_number = db.Column(db.String(20), nullable=False)
    in_time = db.Column(db.DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Kolkata')))
    out_time = db.Column(db.DateTime, nullable=True)
    cost = db.Column(db.Float, nullable=True)
    
    parking_lot = db.relationship('Parking_lot', backref='bookings')

@login_manager.user_loader
def load_user(user_id):
    # Using the recommended method instead of Query.get()
    return db.session.get(User, int(user_id))

# Home route
@app.route('/')
def home():
    return render_template('home.html')

# Authentication routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    # If user is already logged in, logout first to allow new registration
    if current_user.is_authenticated:
        logout_user()
        flash('You have been logged out to register a new account.', 'info')
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash('Username or email already exists.', 'danger')
            return redirect(url_for('register'))

        new_user = User(username=username, email=email, role='user')
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('auth/register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    # If user is already logged in, logout first to allow login with different account
    if current_user.is_authenticated:
        logout_user()
        flash('You have been logged out to login with a different account.', 'info')
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            if user.is_admin():
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('user_dashboard'))
        flash('Invalid username or password.', 'danger')
    return render_template('auth/login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

# Admin routes
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin():
        return redirect(url_for('home'))
    
    lots = Parking_lot.query.all()
    total_spots = 0
    total_occupied = 0
    
    for lot in lots:
        lot.occupied_spots = Parking_spot.query.filter_by(parking_lot_id=lot.id, status='O').count()
        lot.available_spots = lot.max_no_spots - lot.occupied_spots
        total_spots += lot.max_no_spots
        total_occupied += lot.occupied_spots

    stats = {
        'total_users': User.query.filter_by(role='user').count(),
        'total_lots': len(lots),
        'total_spots': total_spots,
        'occupied_spots': total_occupied
    }
    
    # Prepare data for admin dashboard charts
    # 1. Revenue by parking lot
    lot_revenue = {}
    for lot in lots:
        bookings = Booking.query.filter(
            Booking.parking_lot_id == lot.id,
            Booking.out_time.isnot(None)
        ).all()
        revenue = sum(booking.cost for booking in bookings if booking.cost)
        lot_revenue[lot.name] = revenue
    
    # 2. Bookings by day of week
    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    bookings_by_day = {day: 0 for day in days_of_week}
    
    all_bookings = Booking.query.filter(Booking.out_time.isnot(None)).all()
    for booking in all_bookings:
        if booking.in_time:
            # Ensure timezone awareness
            if booking.in_time.tzinfo is None:
                in_time = pytz.timezone('Asia/Kolkata').localize(booking.in_time)
            else:
                in_time = booking.in_time
                
            day_of_week = days_of_week[in_time.weekday()]
            bookings_by_day[day_of_week] += 1
    
    # 3. Occupancy rate over time (last 7 days)
    import json
    from datetime import timedelta
    
    # Get today's date in IST
    today = datetime.now(pytz.timezone('Asia/Kolkata')).date()
    
    # Initialize data for the last 7 days
    date_labels = []
    occupancy_data = []
    
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        date_str = date.strftime('%Y-%m-%d')
        date_labels.append(date.strftime('%b %d'))
        
        # Count bookings for this date
        day_start = datetime.combine(date, datetime.min.time())
        day_start = pytz.timezone('Asia/Kolkata').localize(day_start)
        
        day_end = datetime.combine(date, datetime.max.time())
        day_end = pytz.timezone('Asia/Kolkata').localize(day_end)
        
        day_bookings = Booking.query.filter(
            Booking.in_time >= day_start,
            Booking.in_time <= day_end
        ).count()
        
        # Calculate occupancy as a percentage of total spots
        occupancy_percent = 0
        if total_spots > 0:
            occupancy_percent = (day_bookings / total_spots) * 100
        
        occupancy_data.append(round(occupancy_percent, 1))
    
    # Prepare chart data
    admin_chart_data = {
        'lot_revenue': {
            'labels': list(lot_revenue.keys()),
            'data': list(lot_revenue.values())
        },
        'bookings_by_day': {
            'labels': list(bookings_by_day.keys()),
            'data': list(bookings_by_day.values())
        },
        'occupancy_trend': {
            'labels': date_labels,
            'data': occupancy_data
        }
    }
    
    return render_template('admin/dashboard.html', 
                          lots=lots, 
                          stats=stats, 
                          admin_chart_data=json.dumps(admin_chart_data))

@app.route('/admin/lot/new', methods=['GET', 'POST'])
@login_required
def create_parking_lot():
    if not current_user.is_admin(): return redirect(url_for('home'))
    if request.method == 'POST':
        # Backend validation
        name = request.form.get('name')
        # ... add more validation ...
        
        new_lot = Parking_lot(
            name=name,
            address=request.form.get('address'),
            pincode=request.form.get('pincode'),
            price_per_hour=float(request.form.get('price_per_hour')),
            max_no_spots=int(request.form.get('max_no_spots'))
        )
        db.session.add(new_lot)
        db.session.flush()  # Get the ID for the new lot

        # Create parking spots for the lot
        for i in range(1, new_lot.max_no_spots + 1):
            spot = Parking_spot(spot_number=f"S{i}", parking_lot_id=new_lot.id)
            db.session.add(spot)
        
        db.session.commit()
        flash('Parking lot and spots created successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/create_lot.html')

@app.route('/admin/lot/delete/<int:lot_id>', methods=['POST'])
@login_required
def delete_parking_lot(lot_id):
    if not current_user.is_admin(): return redirect(url_for('home'))
    
    lot = Parking_lot.query.get_or_404(lot_id)
    if Parking_spot.query.filter_by(parking_lot_id=lot_id, status='O').count() > 0:
        flash('Cannot delete a lot with occupied spots.', 'danger')
    else:
        db.session.delete(lot)
        db.session.commit()
        flash('Parking lot deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/spot_search', methods=['GET'])
@login_required
def admin_spot_search():
    if not current_user.is_admin(): return redirect(url_for('home'))
    
    query = request.args.get('query', '').strip()
    lot_id = request.args.get('lot_id', None)
    
    spots = []
    lots = Parking_lot.query.all()
    
    if query:
        # Base query
        spots_query = Parking_spot.query.filter(Parking_spot.spot_number.ilike(f'%{query}%'))
        
        # If lot_id is provided, filter by that lot
        if lot_id and lot_id.isdigit():
            spots_query = spots_query.filter_by(parking_lot_id=int(lot_id))
            
        # Get all spots that match, not just the first one
        spots = spots_query.all()
        
        # For each spot, get its booking info if occupied
        for spot in spots:
            if spot.status == 'O':
                spot.current_booking = Booking.query.filter_by(parking_spot_id=spot.id, out_time=None).first()
            else:
                spot.current_booking = None

    return render_template('admin/search_spot_results.html', spots=spots, query=query, lot_id=lot_id, lots=lots)

@app.route('/admin/users')
@login_required
def view_users():
    if not current_user.is_admin(): return redirect(url_for('home'))
    users = User.query.filter_by(role='user').all()
    return render_template('admin/view_users.html', users=users)

# User routes
@app.route('/dashboard')
@login_required
def user_dashboard():
    lots = Parking_lot.query.all()
    for lot in lots:
        lot.available_spots = Parking_spot.query.filter_by(parking_lot_id=lot.id, status='A').count()
    
    active_booking = Booking.query.filter_by(user_id=current_user.id, out_time=None).first()
    booking_history = Booking.query.filter(Booking.user_id == current_user.id, Booking.out_time.isnot(None)).order_by(Booking.in_time.desc()).all()
    
    # Prepare data for charts
    # 1. Spending by parking lot
    lot_spending = {}
    for booking in booking_history:
        lot_name = booking.parking_lot.name
        if lot_name in lot_spending:
            lot_spending[lot_name] += booking.cost
        else:
            lot_spending[lot_name] = booking.cost
    
    # 2. Parking duration by day of week
    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    parking_by_day = {day: 0 for day in days_of_week}
    
    for booking in booking_history:
        if booking.out_time and booking.in_time:
            # Ensure both are timezone-aware
            if booking.in_time.tzinfo is None:
                in_time = pytz.timezone('Asia/Kolkata').localize(booking.in_time)
            else:
                in_time = booking.in_time
                
            if booking.out_time.tzinfo is None:
                out_time = pytz.timezone('Asia/Kolkata').localize(booking.out_time)
            else:
                out_time = booking.out_time
                
            duration = (out_time - in_time).total_seconds() / 3600  # hours
            day_of_week = days_of_week[in_time.weekday()]
            parking_by_day[day_of_week] += duration
    
    # 3. Number of bookings per month
    monthly_bookings = {}
    for booking in booking_history:
        month_name = booking.in_time.strftime('%B')
        if month_name in monthly_bookings:
            monthly_bookings[month_name] += 1
        else:
            monthly_bookings[month_name] = 1
    
    # Prepare chart data as JSON
    import json
    chart_data = {
        'lot_spending': {
            'labels': list(lot_spending.keys()),
            'data': list(lot_spending.values())
        },
        'parking_by_day': {
            'labels': list(parking_by_day.keys()),
            'data': list(parking_by_day.values())
        },
        'monthly_bookings': {
            'labels': list(monthly_bookings.keys()),
            'data': list(monthly_bookings.values())
        }
    }

    return render_template('user/dashboard.html', 
                           lots=lots, 
                           active_booking=active_booking, 
                           history=booking_history,
                           chart_data=json.dumps(chart_data))

@app.route('/reserve/<int:lot_id>', methods=['GET', 'POST'])
@login_required
def reserve_spot(lot_id):
    if Booking.query.filter_by(user_id=current_user.id, out_time=None).first():
        flash('You already have an active booking.', 'warning')
        return redirect(url_for('user_dashboard'))

    lot = Parking_lot.query.get_or_404(lot_id)
    # Calculate available spots for this lot
    lot.available_spots = Parking_spot.query.filter_by(parking_lot_id=lot.id, status='A').count()
    
    if request.method == 'POST':
        vehicle_number = request.form.get('vehicle_number')
        
        # Auto-assign the first available spot
        spot = Parking_spot.query.filter_by(parking_lot_id=lot_id, status='A').first()
        if not spot:
            flash('Sorry, no spots are available in this lot.', 'danger')
            return redirect(url_for('user_dashboard'))

        spot.status = 'O'
        spot.user_id = current_user.id

        # Create the booking with timezone-aware datetime
        new_booking = Booking(
            user_id=current_user.id,
            parking_lot_id=lot.id,
            parking_spot_id=spot.id,
            vehicle_number=vehicle_number,
            in_time=datetime.now(pytz.timezone('Asia/Kolkata'))
        )
        db.session.add(new_booking)
        db.session.commit()
        flash(f'Spot {spot.spot_number} in {lot.name} reserved successfully!', 'success')
        return redirect(url_for('user_dashboard'))

    return render_template('user/reserve.html', lot=lot)

@app.route('/release/<int:booking_id>', methods=['POST'])
@login_required
def release_spot(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id:
        flash('This is not your booking.', 'danger')
        return redirect(url_for('user_dashboard'))
        
    spot = booking.parking_spot
    lot = booking.parking_lot
    
    # Set the end time with the timezone
    booking.out_time = datetime.now(pytz.timezone('Asia/Kolkata'))
    
    # Ensure both datetimes are timezone-aware before subtraction
    in_time = booking.in_time
    if in_time.tzinfo is None:
        in_time = pytz.timezone('Asia/Kolkata').localize(in_time)
    
    # Calculate duration and cost
    duration_seconds = (booking.out_time - in_time).total_seconds()
    duration_hours = max(0, duration_seconds / 3600)  # Ensure non-negative duration
    booking.cost = round(duration_hours * lot.price_per_hour, 2)

    # Update spot status
    spot.status = 'A'
    spot.user_id = None
    
    db.session.commit()
    flash(f'Spot released. Total cost: ₹{booking.cost}', 'success')
    return redirect(url_for('user_dashboard'))

# API routes
@app.route('/api/lots', methods=['GET'])
def api_get_lots():
    lots = Parking_lot.query.all()
    lots_data = []
    for lot in lots:
        lots_data.append({
            'id': lot.id,
            'name': lot.name,
            'address': lot.address,
            'pincode': lot.pincode,
            'price_per_hour': lot.price_per_hour,
            'capacity': lot.max_no_spots
        })
    return jsonify(lots_data)

@app.route('/api/spots/<int:spot_id>', methods=['GET'])
def api_get_spot(spot_id):
    spot = Parking_spot.query.get_or_404(spot_id)
    status = 'Available' if spot.status == 'A' else 'Occupied'
    return jsonify({
        'spot_id': spot.id,
        'spot_number': spot.spot_number,
        'lot_id': spot.parking_lot_id,
        'status': status
    })

@app.route('/api/users', methods=['GET'])
def api_get_users():
    users = User.query.filter_by(role='user').all()
    users_data = [{'id': user.id, 'username': user.username, 'email': user.email} for user in users]
    return jsonify(users_data)

# Create database and admin user
with app.app_context():
    # Create tables if they don't exist
    db.create_all()
    
    # Check if admin user exists before trying to create one
    admin_exists = db.session.query(User.id).filter_by(username='admin').first() is not None
    
    if not admin_exists:
        try:
            admin = User(username='admin', email='admin@gmail.com', role='admin')
            admin.set_password('admin')
            db.session.add(admin)
            db.session.commit()
        except Exception as e:
            # Silently rollback in case of any issues
            db.session.rollback()

@app.route('/admin/lot/edit/<int:lot_id>', methods=['GET', 'POST'])
@login_required
def edit_parking_lot(lot_id):
    if not current_user.is_admin(): return redirect(url_for('home'))
    
    lot = Parking_lot.query.get_or_404(lot_id)
    occupied_spots = Parking_spot.query.filter_by(parking_lot_id=lot.id, status='O').count()
    
    if request.method == 'POST':
        name = request.form.get('name')
        address = request.form.get('address')
        pincode = request.form.get('pincode')
        price_per_hour = float(request.form.get('price_per_hour'))
        new_max_spots = int(request.form.get('max_no_spots'))
        
        # Validate that new max spots is not less than 1
        if new_max_spots < 1:
            flash('A parking lot must have at least 1 spot.', 'danger')
            return render_template('admin/edit_lot.html', lot=lot, occupied_spots=occupied_spots)
        
        # Validate that new max spots is not less than occupied spots
        if new_max_spots < occupied_spots:
            flash(f'Cannot reduce spots below current occupancy ({occupied_spots} spots in use).', 'danger')
            return render_template('admin/edit_lot.html', lot=lot, occupied_spots=occupied_spots)
        
        # Update lot details
        lot.name = name
        lot.address = address
        lot.pincode = pincode
        lot.price_per_hour = price_per_hour
        
        # Handle spot changes
        if new_max_spots > lot.max_no_spots:
            # Add new spots
            for i in range(lot.max_no_spots + 1, new_max_spots + 1):
                spot = Parking_spot(spot_number=f"S{i}", parking_lot_id=lot.id)
                db.session.add(spot)
        elif new_max_spots < lot.max_no_spots:
            # Remove unoccupied spots from the highest numbers first
            available_spots = Parking_spot.query.filter_by(
                parking_lot_id=lot.id, 
                status='A'
            ).all()
            
            # Sort spots numerically by extracting the number from spot_number (e.g., "S5" -> 5)
            available_spots.sort(key=lambda x: int(x.spot_number[1:]), reverse=True)
            
            # Remove the required number of spots from the highest numbers
            spots_to_remove_count = lot.max_no_spots - new_max_spots
            spots_to_remove = available_spots[:spots_to_remove_count]
            
            for spot in spots_to_remove:
                db.session.delete(spot)
                
        # Update the max_no_spots value
        lot.max_no_spots = new_max_spots
        
        db.session.commit()
        flash('Parking lot updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
        
    return render_template('admin/edit_lot.html', lot=lot, occupied_spots=occupied_spots)

if __name__ == '__main__':
    app.run(debug=True)
