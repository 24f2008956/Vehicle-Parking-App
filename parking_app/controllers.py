from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from .models import db, User, Parking_lot, Parking_spot, Booking
from datetime import datetime
import json

main = Blueprint('main', __name__)

# Helper function to standardize spot number formatting
def format_spot_number(number):
    """
    Standardize spot number format to ensure consistent lexicographical ordering.
    Accepts either a number or a string with 'S' prefix.
    Always returns format 'S{number}' with uppercase S.
    """
    if isinstance(number, int):
        return f"S{number}"
    elif isinstance(number, str):
        # If it's a string, extract the number and reformat
        try:
            # Remove any 'S' or 's' prefix and convert to int
            num = int(number.upper().replace('S', ''))
            return f"S{num}"
        except ValueError:
            # If conversion fails, return original string with 'S' prefix
            return f"S{number}"
    return f"S{number}"

@main.route('/')
def home():
    return render_template('home.html')

# --- Authentication Routes ---
@main.route('/register', methods=['GET', 'POST'])
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
            return redirect(url_for('main.register'))

        new_user = User(username=username, email=email, role='user')
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('main.login'))
    return render_template('auth/register.html')

@main.route('/login', methods=['GET', 'POST'])
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
                return redirect(url_for('main.admin_dashboard'))
            return redirect(url_for('main.user_dashboard'))
        flash('Invalid username or password.', 'danger')
    return render_template('auth/login.html')

@main.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.home'))

# --- Admin Routes ---
@main.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin():
        return redirect(url_for('main.home'))
    
    lots = Parking_lot.query.all()
    total_spots = 0
    occupied_spots = 0
    
    for lot in lots:
        lot.occupied_spots = Parking_spot.query.filter_by(parking_lot_id=lot.id, status='O').count()
        lot.available_spots = lot.max_no_spots - lot.occupied_spots
        total_spots += lot.max_no_spots
        occupied_spots += lot.occupied_spots

    stats = {
        'total_users': User.query.filter_by(role='user').count(),
        'total_lots': len(lots),
        'total_spots': total_spots,
        'occupied_spots': occupied_spots
    }
    
    # Chart data
    import json
    from datetime import timedelta
    
    # Mock chart data (would be replaced with real data in production)
    admin_chart_data = {
        'lot_revenue': {
            'labels': [lot.name for lot in lots],
            'data': [round(100 * (i + 1)) for i, _ in enumerate(lots)]  # Mock revenue data
        },
        'bookings_by_day': {
            'labels': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
            'data': [5, 7, 8, 10, 12, 15, 6]  # Mock booking data
        },
        'occupancy_trend': {
            'labels': [(datetime.utcnow() - timedelta(days=i)).strftime('%d/%m') for i in range(6, -1, -1)],
            'data': [60, 65, 70, 75, 68, 72, 80]  # Mock occupancy data
        }
    }
    
    return render_template('admin/dashboard.html', lots=lots, stats=stats, admin_chart_data=json.dumps(admin_chart_data))

@main.route('/admin/lot/new', methods=['GET', 'POST'])
@login_required
def create_parking_lot():
    if not current_user.is_admin(): return redirect(url_for('main.home'))
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

        # Create parking spots for the lot with sequential numbers starting from 1
        max_spots = new_lot.max_no_spots
        for i in range(1, max_spots + 1):
            spot = Parking_spot(spot_number=format_spot_number(i), parking_lot_id=new_lot.id)
            db.session.add(spot)
        
        db.session.commit()
        flash('Parking lot and spots created successfully!', 'success')
        return redirect(url_for('main.admin_dashboard'))
    return render_template('admin/create_lot.html')

@main.route('/admin/lot/delete/<int:lot_id>', methods=['POST'])
@login_required
def delete_parking_lot(lot_id):
    if not current_user.is_admin(): return redirect(url_for('main.home'))
    
    lot = Parking_lot.query.get_or_404(lot_id)
    if Parking_spot.query.filter_by(parking_lot_id=lot_id, status='O').count() > 0:
        flash('Cannot delete a lot with occupied spots.', 'danger')
    else:
        db.session.delete(lot)
        db.session.commit()
        flash('Parking lot deleted successfully.', 'success')
    return redirect(url_for('main.admin_dashboard'))

@main.route('/admin/spot_search', methods=['GET'])
@login_required
def admin_spot_search():
    if not current_user.is_admin(): return redirect(url_for('main.home'))
    
    query = request.args.get('query', '').strip()
    spot = None
    booking = None
    if query:
        spot = Parking_spot.query.filter(Parking_spot.spot_number.ilike(f'%{query}%')).first()
        if spot and spot.status == 'O':
            booking = Booking.query.filter_by(parking_spot_id=spot.id, out_time=None).first()

    return render_template('admin/search_spot_results.html', spot=spot, booking=booking, query=query)

@main.route('/admin/users')
@login_required
def view_users():
    if not current_user.is_admin(): return redirect(url_for('main.home'))
    users = User.query.filter_by(role='user').all()
    return render_template('admin/view_users.html', users=users)


# --- User Routes ---
@main.route('/dashboard')
@login_required
def user_dashboard():
    lots = Parking_lot.query.all()
    for lot in lots:
        lot.available_spots = Parking_spot.query.filter_by(parking_lot_id=lot.id, status='A').count()
    
    active_booking = Booking.query.filter_by(user_id=current_user.id, out_time=None).first()
    booking_history = Booking.query.filter(Booking.user_id == current_user.id, Booking.out_time.isnot(None)).order_by(Booking.in_time.desc()).all()

    return render_template('user/dashboard.html', lots=lots, active_booking=active_booking, history=booking_history)

@main.route('/reserve/<int:lot_id>', methods=['GET', 'POST'])
@login_required
def reserve_spot(lot_id):
    if Booking.query.filter_by(user_id=current_user.id, out_time=None).first():
        flash('You already have an active booking.', 'warning')
        return redirect(url_for('main.user_dashboard'))

    lot = Parking_lot.query.get_or_404(lot_id)
    if request.method == 'POST':
        vehicle_number = request.form.get('vehicle_number')
        
        # Auto-assign the first available spot
        spot = Parking_spot.query.filter_by(parking_lot_id=lot_id, status='A').first()
        if not spot:
            flash('Sorry, no spots are available in this lot.', 'danger')
            return redirect(url_for('main.user_dashboard'))

        spot.status = 'O'
        spot.user_id = current_user.id

        new_booking = Booking(
            user_id=current_user.id,
            parking_lot_id=lot.id,
            parking_spot_id=spot.id,
            vehicle_number=vehicle_number
        )
        db.session.add(new_booking)
        db.session.commit()
        flash(f'Spot {spot.spot_number} in {lot.name} reserved successfully!', 'success')
        return redirect(url_for('main.user_dashboard'))

    return render_template('user/reserve.html', lot=lot)

@main.route('/release/<int:booking_id>', methods=['POST'])
@login_required
def release_spot(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id:
        flash('This is not your booking.', 'danger')
        return redirect(url_for('main.user_dashboard'))

    spot = booking.parking_spot
    lot = booking.parking_lot
    
    booking.out_time = datetime.utcnow()
    duration_seconds = (booking.out_time - booking.in_time).total_seconds()
    duration_hours = duration_seconds / 3600
    booking.cost = round(duration_hours * lot.price_per_hour, 2)
    
    spot.status = 'A'
    spot.user_id = None
    
    db.session.commit()
    flash(f'Spot released. Total cost: ₹{booking.cost}', 'success')
    return redirect(url_for('main.user_dashboard'))

@main.route('/admin/lot/edit/<int:lot_id>', methods=['GET', 'POST'])
@login_required
def edit_parking_lot(lot_id):
    if not current_user.is_admin(): return redirect(url_for('main.home'))
    
    lot = Parking_lot.query.get_or_404(lot_id)
    occupied_spots = Parking_spot.query.filter_by(parking_lot_id=lot.id, status='O').count()
    
    if request.method == 'POST':
        name = request.form.get('name')
        address = request.form.get('address')
        pincode = request.form.get('pincode')
        price_per_hour = float(request.form.get('price_per_hour'))
        new_max_spots = int(request.form.get('max_no_spots'))
        
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
            # Get all current spot numbers for this lot
            current_spots = Parking_spot.query.filter_by(parking_lot_id=lot.id).all()
            
            # Normalize all existing spot numbers to ensure consistent format
            for spot in current_spots:
                spot.spot_number = format_spot_number(spot.spot_number)
            
            # Find the highest spot number currently in use
            highest_number = 0
            for spot in current_spots:
                try:
                    # Handle both uppercase and lowercase 'S' in existing spot numbers
                    spot_num = spot.spot_number.upper().replace('S', '')
                    num = int(spot_num)
                    if num > highest_number:
                        highest_number = num
                except (ValueError, AttributeError):
                    pass
            
            # Add new spots with sequential numbers starting from the next available number
            spots_to_add = new_max_spots - lot.max_no_spots
            for i in range(1, spots_to_add + 1):
                new_spot_num = highest_number + i
                spot = Parking_spot(spot_number=format_spot_number(new_spot_num), parking_lot_id=lot.id)
                db.session.add(spot)
                
        elif new_max_spots < lot.max_no_spots:
            # We need to keep only the lowest-numbered spots and remove the rest
            # Get ALL spots (not just available ones)
            all_spots = Parking_spot.query.filter_by(parking_lot_id=lot.id).all()
            
            # Custom sort function to sort by spot number numerically
            def get_spot_number(spot):
                try:
                    # Use a consistent method to extract the number from spot_number
                    spot_num = spot.spot_number.upper().replace('S', '')
                    return int(spot_num)
                except (ValueError, AttributeError):
                    return 0
            
            # Sort all spots by their numeric value (lowest first)
            all_spots.sort(key=get_spot_number)
            
            # Debug: print all spots sorted by number
            spot_numbers_sorted = [f"{spot.spot_number} (#{get_spot_number(spot)})" for spot in all_spots]
            print(f"All spots sorted: {spot_numbers_sorted}")
            
            # Separate occupied spots (these must be kept)
            occupied_spots = [spot for spot in all_spots if spot.status == 'O']
            available_spots = [spot for spot in all_spots if spot.status == 'A']
            
            print(f"Occupied spots: {[spot.spot_number for spot in occupied_spots]}")
            print(f"Available spots: {[spot.spot_number for spot in available_spots]}")
            
            # If we need to keep N spots, and M are occupied, we can keep at most (N-M) available spots
            available_spots_to_keep = new_max_spots - len(occupied_spots)
            
            # If we need to remove spots, remove the highest-numbered available spots
            if available_spots_to_keep < len(available_spots):
                # Sort available spots by number (highest first)
                available_spots.sort(key=get_spot_number, reverse=True)
                
                # Keep only the lowest-numbered available spots by removing the highest first
                spots_to_remove = available_spots[:len(available_spots) - available_spots_to_keep]
                spots_to_keep = available_spots[len(available_spots) - available_spots_to_keep:]
                
                print(f"Available spots to keep: {[spot.spot_number for spot in spots_to_keep]}")
                print(f"Spots to remove: {[spot.spot_number for spot in spots_to_remove]}")
                
                # Delete the spots that are not being kept (highest numbers first)
                for spot in spots_to_remove:
                    db.session.delete(spot)
                    
            # No else needed - if available_spots_to_keep >= len(available_spots), we keep all available spots
                
        # Update the max_no_spots value
        lot.max_no_spots = new_max_spots
        
        # Ensure we commit the deletions before retrieving the spots for renumbering
        db.session.flush()
        
        # Renumber all spots sequentially to ensure no gaps
        all_spots = Parking_spot.query.filter_by(parking_lot_id=lot.id).all()
        
        # Debug: print all spots after deletions and before renumbering
        print(f"All spots after deletions: {[spot.spot_number for spot in all_spots]}")
        
        # Sort spots by their current number
        def get_spot_number(spot):
            try:
                # Extract the numeric part, regardless of case (S or s)
                spot_num = spot.spot_number.upper().replace('S', '')
                return int(spot_num)
            except (ValueError, AttributeError):
                return 0
        
        # Sort spots numerically (lowest first)
        all_spots.sort(key=get_spot_number)
        
        # Debug: print sorted spot numbers 
        spot_numbers_sorted = [f"{spot.spot_number}" for spot in all_spots]
        print(f"All spots after sorting: {spot_numbers_sorted}")
        
        # Renumber them sequentially starting from 1
        for i, spot in enumerate(all_spots, 1):
            old_number = spot.spot_number
            spot.spot_number = format_spot_number(i)  # Use helper function for consistent formatting
            print(f"Renumbered: {old_number} -> {spot.spot_number}")
        
        # Final check
        all_spots_after = Parking_spot.query.filter_by(parking_lot_id=lot.id).all()
        final_numbers = [spot.spot_number for spot in all_spots_after]
        print(f"Final spot numbers: {final_numbers}")
        
        db.session.commit()
        flash('Parking lot updated successfully!', 'success')
        return redirect(url_for('main.admin_dashboard'))
        
    return render_template('admin/edit_lot.html', lot=lot, occupied_spots=occupied_spots)
