from flask import Flask, jsonify, request
from flask_cors import CORS  # Import CORS
from firebase_admin import credentials, initialize_app, db, storage
from datetime import datetime, timedelta
import psycopg2
from PIL import Image
import io
import pytz
from datetime import datetime
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)  # อนุญาต CORS ทุกโดเมน

# Connection String สำหรับ Neon PostgreSQL
conn_string = "postgresql://facerecon_owner:NsqA5QSpbT2G@ep-super-bonus-a1hmwxyx.ap-southeast-1.aws.neon.tech/facerecon?sslmode=require"

# Firebase Config
cred = credentials.Certificate('parth.json')
initialize_app(cred, {
    'storageBucket': 'face-recognition-459a6.appspot.com',
    'databaseURL': 'https://face-recognition-459a6-default-rtdb.asia-southeast1.firebasedatabase.app/'})
bucket = storage.bucket()

bangkok_tz = pytz.timezone('Asia/Bangkok')



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
        query = "SELECT user_id, name, room_number, total_attendance, last_attendance_time, dominant_emotion,timestamp FROM logs;"
        cursor.execute(query)
        rows = cursor.fetchall()

        # แปลงข้อมูลเป็น JSON
        users = [{"user_id": row[0], "name": row[1], "room_number": row[2], "total_attendance": row[3], "last_attendance_time": row[4], "dominant_emotion": row[5], "timestamp": row[6] } for row in rows]

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


@app.route('/api/realtime-data', methods=['GET'])
def get_realtime_data_with_images():
    try:
        # ✅ เชื่อมต่อ PostgreSQL
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # ✅ ดึงข้อมูลจากตาราง users
        cursor.execute("SELECT id, name, role, standing, studyClass, total_attendance, last_attendance_time FROM users;")
        users = cursor.fetchall()
        cursor.close()
        conn.close()

        if not users:
            return jsonify({'message': 'No data found'}), 404

        # ✅ เชื่อมต่อ Firebase Storage
        bucket = storage.bucket()

        # ✅ เพิ่ม URL รูปภาพให้แต่ละผู้ใช้
        for user in users:
            user_id = str(user['id'])  # ใช้ `id` จาก PostgreSQL
            image_path = f'Images/{user_id}.png'
            blob = bucket.blob(image_path)

            try:
                if blob.exists():
                    expiration_time = datetime.utcnow() + timedelta(hours=24)  # URL มีอายุ 24 ชั่วโมง
                    user['image_url'] = blob.generate_signed_url(expiration=expiration_time)
                else:
                    user['image_url'] = None  # ไม่มีรูป
            except Exception as e:
                user['image_url'] = None  # หากเกิดข้อผิดพลาด

        return jsonify(users), 200

    except Exception as e:
        print(f"Error fetching data with images: {e}")
        return jsonify({'error': str(e)}), 500

    
@app.route('/api/delete-user/<string:user_id>', methods=['DELETE'])
def delete_user(user_id):
    try:
        # ✅ เชื่อมต่อ PostgreSQL
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()

        # ✅ ตรวจสอบว่า user_id มีอยู่ใน users หรือไม่
        check_user_query = "SELECT 1 FROM users WHERE id = %s;"
        cursor.execute(check_user_query, (user_id,))
        user_exists = cursor.fetchone()

        if not user_exists:
            cursor.close()
            conn.close()
            return jsonify({'error': 'User not found in users table'}), 404


        # ✅ ลบข้อมูลจากตาราง users
        delete_users_query = "DELETE FROM users WHERE id = %s;"
        cursor.execute(delete_users_query, (user_id,))

        conn.commit()
        cursor.close()
        conn.close()


        # ✅ ลบรูปโปรไฟล์จาก Firebase Storage
        bucket = storage.bucket()
        image_path = f'Images/{user_id}.png'
        blob = bucket.blob(image_path)
        if blob.exists():
            blob.delete()

        # ✅ ลบโฟลเดอร์ trainface/{user_id}/ ทั้งหมด
        folder_path = f'trainface/{user_id}/'
        blobs = bucket.list_blobs(prefix=folder_path)
        for blob in blobs:
            blob.delete()

        return jsonify({'message': f'User {user_id} and all related data deleted successfully'}), 200

    except Exception as e:
        print(f"Error deleting user {user_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/update-user/<string:user_id>', methods=['PUT'])
def update_user(user_id):
    try:
        data = request.form.to_dict()
        new_image = request.files.get('image')  # รับไฟล์ภาพใหม่

        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()

        # ✅ เช็คว่ามี user ใน users หรือไม่
        check_users_query = "SELECT 1 FROM users WHERE id = %s;"
        cursor.execute(check_users_query, (user_id,))
        user_exists = cursor.fetchone()

        if not user_exists:
            cursor.close()
            conn.close()
            return jsonify({'error': 'User not found in users table'}), 404

        # ✅ อัปเดตข้อมูลใน users table
        update_users_query = """
        UPDATE users
        SET name = %s, role = %s, standing = %s, studyClass = %s, total_attendance = %s, last_attendance_time = %s
        WHERE id = %s;
        """
        cursor.execute(update_users_query, (
            data.get('name'),
            data.get('role'),
            data.get('standing', 'Com-Tech'),
            data.get('studyClass', '-'),
            data.get('total_attendance', 0),
            data.get('last_attendance_time'),
            user_id
        ))

        # ✅ เช็คว่ามี user_id ใน logs หรือไม่
        check_logs_query = "SELECT 1 FROM logs WHERE user_id = %s;"
        cursor.execute(check_logs_query, (user_id,))
        logs_exists = cursor.fetchone()

        # ✅ ถ้า user_id มีอยู่ใน logs → อัปเดตชื่อใน logs ด้วย
        if logs_exists:
            update_logs_query = """
            UPDATE logs
            SET name = %s
            WHERE user_id = %s;
            """
            cursor.execute(update_logs_query, (data.get('name'), user_id))

        conn.commit()
        cursor.close()
        conn.close()

        # ✅ อัปโหลดรูปภาพใหม่ (ถ้ามี)
        if new_image:
            image = Image.open(new_image)
            image = image.resize((216, 216))  # Resize ภาพเป็น 216x216
            image_io = io.BytesIO()
            image.save(image_io, format='PNG')  # บันทึกเป็น PNG
            image_io.seek(0)

            # ✅ อัปโหลดไฟล์ใหม่ไปที่ Firebase Storage (ใช้ user_id เป็นชื่อไฟล์)
            bucket = storage.bucket()
            image_path = f'Images/{user_id}.png'
            blob = bucket.blob(image_path)
            blob.upload_from_file(image_io, content_type='image/png')

        return jsonify({'message': 'User updated successfully'}), 200

    except Exception as e:
        print(f"Error updating user {user_id}: {e}")
        return jsonify({'error': str(e)}), 500





@app.route('/api/add-user', methods=['POST'])
def add_user():
    try:
        data = request.form.to_dict()
        profile_image = request.files.get('image')  # รูปโปรไฟล์
        face_images = request.files.getlist('faceImages')  # ✅ รูปใบหน้าหลายไฟล์

        if not data.get('name') or not data.get('role'):
            return jsonify({'error': 'Missing required fields'}), 400

        # ✅ เพิ่มผู้ใช้ลง PostgreSQL
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # ✅ ดึงเวลาปัจจุบัน (Bangkok)
        current_time = datetime.now(bangkok_tz).strftime("%Y-%m-%d %H:%M:%S")

        # ✅ INSERT ลง PostgreSQL และคืนค่า `id`
        insert_query = """
        INSERT INTO users (name, role, standing, studyClass, total_attendance, last_attendance_time)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;
        """
        cursor.execute(insert_query, (
            data.get('name'),
            data.get('role'),
            data.get('standing', 'Com-Tech'),
            data.get('studyClass', '-'),
            0,
            current_time
        ))

        new_user = cursor.fetchone()
        user_id = str(new_user['id'])  # ✅ `id` ที่เพิ่งสร้าง
        conn.commit()
        cursor.close()
        conn.close()

        # ✅ อัปโหลด **รูปโปรไฟล์**
        if profile_image:
            image = Image.open(profile_image)
            image = image.resize((216, 216))
            image_io = io.BytesIO()
            image.save(image_io, format='PNG')
            image_io.seek(0)

            bucket = storage.bucket()
            image_path = f'Images/{user_id}.png'  # ใช้ user_id เป็นชื่อไฟล์
            blob = bucket.blob(image_path)
            blob.upload_from_file(image_io, content_type='image/png')

        return jsonify({
            'message': 'User added successfully',
            'user_id': user_id,
            'last_attendance_time': current_time
        }), 201

    except Exception as e:
        print(f"Error adding user: {e}")
        return jsonify({'error': str(e)}), 500

    
@app.route('/api/upload-face-images', methods=['POST'])
def upload_face_images():
    try:
        user_id = request.form.get('user_id')  # ✅ เปลี่ยนจาก Room_Number เป็น user_id
        face_images = request.files.getlist('faceImages')

        if not user_id or not face_images:
            return jsonify({'error': 'Missing user_id or face images'}), 400

        # ✅ อัปโหลดรูปภาพไปที่ Firebase Storage
        folder_path = f'trainface/{user_id}/'
        bucket = storage.bucket()

        uploaded_files = []
        for idx, face_image in enumerate(face_images):
            face_io = io.BytesIO(face_image.read())  # ✅ อ่านไฟล์ครั้งเดียว
            face_path = f'{folder_path}face_{idx}.png'
            blob = bucket.blob(face_path)
            blob.upload_from_file(face_io, content_type='image/png')

            uploaded_files.append(blob.public_url)

        return jsonify({
            'message': 'Face images uploaded successfully',
            'user_id': user_id,
            'uploaded_files': uploaded_files
        }), 201

    except Exception as e:
        print(f"Error uploading face images: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
