from flask import Flask, jsonify, request
from flask_cors import CORS  # Import CORS
from firebase_admin import credentials, initialize_app, db, storage
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)  # อนุญาต CORS ทุกโดเมน

# Firebase Config
cred = credentials.Certificate('parth.json')
initialize_app(cred, {
    'storageBucket': 'face-recognition-459a6.appspot.com',
    'databaseURL': 'https://face-recognition-459a6-default-rtdb.asia-southeast1.firebasedatabase.app/'})

# API สำหรับตรวจสอบการ Login
@app.route('/api/login', methods=['POST'])
def login():
    try:
        # รับข้อมูล username และ password จาก client
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400

        # ชี้ไปยัง path 'admin' ใน Realtime Database
        ref = db.reference('admin')
        admins = ref.get()  # ดึงข้อมูลทั้งหมดจาก path 'admin'

        # ค้นหาผู้ใช้ที่ตรงกับ username และ password
        for admin_id, admin_data in admins.items():
            if admin_data.get('user') == username and admin_data.get('password') == password:
                return jsonify({'message': 'Login successful', 'user': username}), 200

        # หากไม่มีผู้ใช้ที่ตรงกัน
        return jsonify({'error': 'Invalid username or password'}), 401

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/images', methods=['GET'])
def get_images():
    try:
        bucket = storage.bucket()
        blobs = bucket.list_blobs(prefix="Images/")
        expiration_time = datetime.utcnow() + timedelta(hours=24)
        image_urls = [blob.generate_signed_url(expiration=expiration_time) for blob in blobs]
        return jsonify({"images": image_urls})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
