from flask import Flask, jsonify, request
from flask_cors import CORS  # Import CORS
from firebase_admin import credentials, initialize_app, db, storage
from datetime import datetime, timedelta
import psycopg2
from PIL import Image
import io
import pytz
from datetime import datetime

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
        # ดึงข้อมูลทั้งหมดจาก Firebase Realtime Database (path: "room")
        ref = db.reference('room')
        data = ref.get()

        if not data:
            return jsonify({'message': 'No data found'}), 404

        # สร้าง bucket สำหรับเชื่อมต่อ Firebase Storage
        bucket = storage.bucket()

        # เพิ่ม URL รูปภาพให้แต่ละรายการใน data
        for user_id, user_data in data.items():
            try:
                # สร้าง path ของรูปใน Firebase Storage
                image_path = f'Images/{user_id}.png'
                blob = bucket.blob(image_path)

                # ตรวจสอบว่ามีรูปใน bucket หรือไม่ และสร้าง signed URL
                if blob.exists():
                    expiration_time = datetime.utcnow() + timedelta(hours=24)  # URL มีอายุ 24 ชั่วโมง
                    image_url = blob.generate_signed_url(expiration=expiration_time)
                    user_data['image_url'] = image_url
                else:
                    user_data['image_url'] = None  # หากไม่มีรูปใน bucket
            except Exception as e:
                user_data['image_url'] = None  # กรณีเกิดข้อผิดพลาดในการดึงรูป

        return jsonify(data), 200

    except Exception as e:
        print(f"Error fetching data with images: {e}")
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/delete-user/<string:user_id>', methods=['DELETE'])
def delete_user(user_id):
    try:
        # ✅ ลบข้อมูลจาก Firebase Realtime Database
        ref = db.reference(f'room/{user_id}')
        if ref.get() is None:
            return jsonify({'error': 'User not found'}), 404
        ref.delete()

        # ✅ ลบรูปภาพโปรไฟล์จาก Firebase Storage
        bucket = storage.bucket()
        image_path = f'Images/{user_id}.png'
        blob = bucket.blob(image_path)
        if blob.exists():
            blob.delete()

        # ✅ ลบ **โฟลเดอร์ trainface/{user_id}/** ทั้งหมด
        folder_path = f'trainface/{user_id}/'
        blobs = bucket.list_blobs(prefix=folder_path)  # ดึงรายการไฟล์ทั้งหมดในโฟลเดอร์นี้

        for blob in blobs:
            blob.delete()  # ลบไฟล์ทั้งหมดในโฟลเดอร์

        return jsonify({'message': f'User {user_id} and all related data deleted successfully'}), 200

    except Exception as e:
        print(f"Error deleting user {user_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/update-user/<string:user_id>', methods=['PUT'])
def update_user(user_id):
    try:
        data = request.form.to_dict()
        new_image = request.files.get('image')  # รับไฟล์ภาพใหม่

        ref = db.reference(f'room/{user_id}')  # ใช้ Room_Number เป็น Key
        user_data = ref.get()

        if not user_data:
            return jsonify({'error': 'User not found'}), 404

        # ✅ ตรวจสอบและลบ key 'id' ออกจาก data ก่อนอัปเดต
        if 'id' in data:
            del data['id']

        # ✅ อัปเดตข้อมูลเฉพาะใน Firebase Realtime Database โดยไม่เพิ่มคอลัมน์ id
        ref.update(data)

        # ✅ ถ้ามีการอัปโหลดรูปใหม่ ให้บันทึกทับรูปเก่า
        if new_image:
            image = Image.open(new_image)
            image = image.resize((216, 216))  # Resize ภาพเป็น 216x216
            image_io = io.BytesIO()
            image.save(image_io, format='PNG')  # บันทึกเป็น PNG
            image_io.seek(0)

            # ✅ อัปโหลดไฟล์ใหม่ไปที่ Firebase Storage (ใช้ Room_Number เป็นชื่อไฟล์)
            bucket = storage.bucket()
            image_path = f'Images/{user_id}.png'  # ใช้ Room_Number เป็นชื่อไฟล์
            blob = bucket.blob(image_path)
            blob.upload_from_file(image_io, content_type='image/png')

        # ✅ อัปเดตชื่อใน PostgreSQL Database ด้วย
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        update_query = """
        UPDATE logs
        SET name = %s
        WHERE user_id = %s
        """
        cursor.execute(update_query, (data['name'], user_id))  # อัปเดตชื่อ
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'message': 'User updated successfully in Firebase and PostgreSQL'}), 200

    except Exception as e:
        print(f"Error updating user {user_id}: {e}")
        return jsonify({'error': str(e)}), 500



@app.route('/api/add-user', methods=['POST'])
def add_user():
    try:
        data = request.form.to_dict()
        new_image = request.files.get('image')

        # ตรวจสอบข้อมูลที่ต้องมี
        if not data.get('name') or not data.get('role'):
            return jsonify({'error': 'Missing required fields'}), 400

        # ค้นหา Room_Number ล่าสุด แล้ว +1 (รักษาฟอร์แมต 3 หลัก)
        ref = db.reference('room')
        existing_users = ref.get()
        if existing_users:
            last_id = max(map(int, existing_users.keys()))  # หาเลขสูงสุดที่มีอยู่
            next_id = f"{last_id + 1:03d}"  # บังคับให้เป็นเลข 3 หลัก
        else:
            next_id = "001"  # ถ้าไม่มีผู้ใช้เลย ให้เริ่มจาก 001

        data['Room_Number'] = next_id
        data['last_attendance_time'] = datetime.now(bangkok_tz).strftime("%Y-%m-%d %H:%M:%S")
        data['total_attendance'] = 0

        # อัปโหลดรูปภาพโปรไฟล์ (ถ้ามี)
        if new_image:
            image = Image.open(new_image)
            image = image.resize((216, 216))
            image_io = io.BytesIO()
            image.save(image_io, format='PNG')
            image_io.seek(0)

            bucket = storage.bucket()
            image_path = f'Images/{next_id}.png'  # ใช้ Room_Number ที่มี 3 หลัก
            blob = bucket.blob(image_path)
            blob.upload_from_file(image_io, content_type='image/png')

        # บันทึกข้อมูลลง Firebase Realtime Database
        ref.child(next_id).set(data)

        return jsonify({'message': 'User added successfully', 'room_number': next_id}), 201

    except Exception as e:
        print(f"Error adding user: {e}")
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/upload-face-images', methods=['POST'])
def upload_face_images():
    try:
        room_number = request.form.get('Room_Number')
        face_images = request.files.getlist('faceImages')

        if not room_number or not face_images:
            return jsonify({'error': 'Missing Room Number or face images'}), 400

        # 🔥 บังคับให้ Room_Number มี 3 หลักเสมอ
        room_number = str(room_number).zfill(3)

        # อัปโหลดรูปภาพไปที่ Firebase Storage
        folder_path = f'trainface/{room_number}/'
        bucket = storage.bucket()

        uploaded_files = []
        for idx, face_image in enumerate(face_images):
            face_io = io.BytesIO(face_image.read())
            face_path = f'{folder_path}face_{idx}.png'
            blob = bucket.blob(face_path)
            blob.upload_from_file(io.BytesIO(face_io.getvalue()), content_type='image/png')

            uploaded_files.append(blob.public_url)

        return jsonify({
            'message': 'Face images uploaded successfully',
            'room_number': room_number,
            'uploaded_files': uploaded_files
        }), 201

    except Exception as e:
        print(f"Error uploading face images: {e}")
        return jsonify({'error': str(e)}), 500

    except Exception as e:
        print(f"Error uploading face images: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
