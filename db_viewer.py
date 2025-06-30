import sqlite3
import sys
import os
import argparse
from tabulate import tabulate

def get_db_path():
    """Get the database path"""
    instance_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
    return os.path.join(instance_dir, 'parking.db')

def check_db_exists(db_path):
    """Check if the database exists"""
    if not os.path.exists(db_path):
        print(f"Database file not found at: {db_path}")
        sys.exit(1)

def get_table_names(cursor):
    """Get all table names from the database"""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    return [table['name'] for table in cursor.fetchall()]

def view_users(cursor):
    """View all users in the database"""
    cursor.execute("SELECT id, username, email, role FROM user")
    users = cursor.fetchall()
    
    if not users:
        print("No users found in the database.")
        return
    
    # Convert to list of dictionaries for tabulate
    user_list = [dict(user) for user in users]
    print(tabulate(user_list, headers="keys", tablefmt="grid"))
    print(f"\nTotal users: {len(users)}")

def view_bookings(cursor):
    """View all bookings in the database"""
    cursor.execute("""
        SELECT b.id, u.username, ps.spot_number, pl.name as lot_name, 
               b.vehicle_number, b.in_time, b.out_time, b.cost
        FROM booking b
        JOIN user u ON b.user_id = u.id
        JOIN parking_spot ps ON b.parking_spot_id = ps.id
        JOIN parking_lot pl ON ps.parking_lot_id = pl.id
        ORDER BY b.in_time DESC
    """)
    bookings = cursor.fetchall()
    
    if not bookings:
        print("No bookings found in the database.")
        return
    
    # Convert to list of dictionaries for tabulate
    booking_list = [dict(booking) for booking in bookings]
    print(tabulate(booking_list, headers="keys", tablefmt="grid"))
    print(f"\nTotal bookings: {len(bookings)}")

def view_lots(cursor):
    """View all parking lots in the database"""
    cursor.execute("""
        SELECT pl.id, pl.name, pl.address, pl.pincode, pl.price_per_hour, pl.max_no_spots,
               COUNT(CASE WHEN ps.status = 'O' THEN 1 END) as occupied_spots,
               COUNT(CASE WHEN ps.status = 'A' THEN 1 END) as available_spots
        FROM parking_lot pl
        LEFT JOIN parking_spot ps ON pl.id = ps.parking_lot_id
        GROUP BY pl.id
    """)
    lots = cursor.fetchall()
    
    if not lots:
        print("No parking lots found in the database.")
        return
    
    # Convert to list of dictionaries for tabulate
    lot_list = [dict(lot) for lot in lots]
    print(tabulate(lot_list, headers="keys", tablefmt="grid"))
    print(f"\nTotal parking lots: {len(lots)}")

def main():
    """Main function"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='View database information')
    parser.add_argument('--table', '-t', choices=['users', 'bookings', 'lots', 'all'], 
                        default='users', help='Table to view (default: users)')
    args = parser.parse_args()
    
    # Get database path and check if it exists
    db_path = get_db_path()
    check_db_exists(db_path)
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all table names
    table_names = get_table_names(cursor)
    print(f"Database: {db_path}")
    print(f"Tables: {', '.join(table_names)}")
    print("=" * 80)
    
    # View requested table(s)
    if args.table == 'users' or args.table == 'all':
        print("\n=== USERS ===")
        view_users(cursor)
    
    if args.table == 'bookings' or args.table == 'all':
        print("\n=== BOOKINGS ===")
        view_bookings(cursor)
    
    if args.table == 'lots' or args.table == 'all':
        print("\n=== PARKING LOTS ===")
        view_lots(cursor)
    
    # Close the connection
    conn.close()
    
    print("\nNOTE: To view users in the web app, login as admin and go to: http://127.0.0.1:5000/admin/users")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
