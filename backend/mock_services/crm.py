import sqlite3
from flask import Flask, request, jsonify
import os

app = Flask(__name__)
# Path to the shared DB (assuming you run this from backend/ root)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'mock_bank.db')

def get_user(pan):
    if not os.path.exists(DB_PATH): return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM customers WHERE pan=?", (pan,))
    user = cursor.fetchone()
    conn.close()
    return user

@app.route('/verify-kyc', methods=['POST'])
def verify():
    pan = request.json.get('pan', '')
    user = get_user(pan)
    
    if user:
        return jsonify({
            "status": "verified",
            "message": "KYC verification complete",
            "name": user['name'],
            "pan": pan
        }), 200
    return jsonify({"status": "failed", "reason": "PAN not found in CRM"}), 404

if __name__ == '__main__': app.run(port=5001)