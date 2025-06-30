from flask import Blueprint, jsonify
from .models import Parking_lot, Parking_spot, User

api = Blueprint('api', __name__)

@api.route('/lots', methods=['GET'])
def get_lots():
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

@api.route('/spots/<int:spot_id>', methods=['GET'])
def get_spot(spot_id):
    spot = Parking_spot.query.get_or_404(spot_id)
    status = 'Available' if spot.status == 'A' else 'Occupied'
    return jsonify({
        'spot_id': spot.id,
        'spot_number': spot.spot_number,
        'lot_id': spot.parking_lot_id,
        'status': status
    })

@api.route('/users', methods=['GET'])
def get_users():
    users = User.query.filter_by(role='user').all()
    users_data = [{'id': user.id, 'username': user.username, 'email': user.email} for user in users]
    return jsonify(users_data)
