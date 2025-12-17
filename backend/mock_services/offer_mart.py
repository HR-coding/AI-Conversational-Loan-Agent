import sqlite3
import os
from flask import Flask, request, jsonify
app = Flask(__name__)

# Get database path - works from any directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.path.dirname(SCRIPT_DIR), 'mock_bank.db')

@app.route('/get-limit', methods=['POST'])
def get_limit():
    try:
        pan = request.json.get('pan') if request.json else None
        if not pan:
            return jsonify({"error": "PAN is required"}), 400
        
        if not os.path.exists(DB_PATH):
            return jsonify({"error": "Database not found"}), 500
            
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT pre_approved_limit FROM customers WHERE pan=?", (pan,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return jsonify({"pre_approved_limit": row['pre_approved_limit']}), 200
        return jsonify({"error": "User not found"}), 404
    except Exception as e:
        print(f"Error in get-limit: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__': 
    print(f"Starting Offer Mart on port 5003, DB at: {DB_PATH}")
    app.run(port=5003)