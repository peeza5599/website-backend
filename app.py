from flask import Flask, jsonify, request
from flask_cors import CORS  # Import CORS
from firebase_admin import credentials, initialize_app, db, storage
from datetime import datetime, timedelta
import psycopg2

app = Flask(__name__)
CORS(app)  # อนุญาต CORS ทุกโดเมน

# Connection String สำหรับ Neon PostgreSQL
conn_string = "postgresql://facerecon_owner:NsqA5QSpbT2G@ep-super-bonus-a1hmwxyx.ap-southeast-1.aws.neon.tech/facerecon?sslmode=require"

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


# ฟังก์ชันสำหรับเชื่อมต่อฐานข้อมูล
def get_db_connection():
    conn = psycopg2.connect(conn_string)
    return conn

# API Endpoint: ดึงข้อมูลจากตาราง (ตัวอย่างตาราง users)
@app.route('/api/users', methods=['GET'])
def get_users():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Query ข้อมูลจากตาราง users
        query = "SELECT user_id, name, room_number, total_attendance, last_attendance_time, dominant_emotion FROM logs;"
        cursor.execute(query)
        rows = cursor.fetchall()

        # แปลงข้อมูลเป็น JSON
        users = [{"user_id": row[0], "name": row[1], "room_number": row[2], "total_attendance": row[3], "last_attendance_time": row[4], "dominant_emotion": row[5] } for row in rows]

        cursor.close()
        conn.close()

        return jsonify(users), 200
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

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
