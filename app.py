from flask import Flask, jsonify, request
from flask_cors import CORS  # Import CORS
from firebase_admin import credentials, initialize_app, db, storage
from datetime import datetime, timedelta
import psycopg2
from PIL import Image
import io

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
        # ลบข้อมูลจาก Firebase Realtime Database
        ref = db.reference(f'room/{user_id}')
        if ref.get() is None:
            return jsonify({'error': 'User not found'}), 404
        ref.delete()

        # ลบรูปภาพจาก Firebase Storage
        bucket = storage.bucket()
        image_path = f'Images/{user_id}.png'
        blob = bucket.blob(image_path)

        if blob.exists():
            blob.delete()

        return jsonify({'message': 'User deleted successfully'}), 200

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

        return jsonify({'message': 'User updated successfully'}), 200

    except Exception as e:
        print(f"Error updating user {user_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/add-user', methods=['POST'])
def add_user():
    try:
        data = request.form.to_dict()  # รับข้อมูลเป็น Dictionary
        new_image = request.files.get('image')  # รับไฟล์รูปภาพ

        # ตรวจสอบว่ามีค่า Room_Number และ Name หรือไม่
        if not data.get('name') or not data.get('Room_Number'):
            return jsonify({'error': 'Missing required fields'}), 400

        room_number = str(data.get('Room_Number'))  # ใช้ Room_Number เป็น Key ใน Firebase
        data['last_attendance_time'] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")  # กำหนดเวลา

        # 📌 แปลงค่าของ total_attendance และ starting_year ให้เป็น int
        if 'total_attendance' in data:
            try:
                data['total_attendance'] = int(data['total_attendance'])
            except ValueError:
                data['total_attendance'] = 0  # ถ้าค่าไม่ใช่ตัวเลข ให้กำหนดเป็น 0

        if 'starting_year' in data:
            try:
                data['starting_year'] = int(data['starting_year'])
            except ValueError:
                data['starting_year'] = datetime.utcnow().year  # ถ้าค่าไม่ใช่ตัวเลข กำหนดเป็นปีปัจจุบัน

        # 📌 ถ้ามีการอัปโหลดรูปภาพ
        if new_image:
            image = Image.open(new_image)
            image = image.resize((216, 216))  # Resize เป็น 216x216
            image_io = io.BytesIO()
            image.save(image_io, format='PNG')
            image_io.seek(0)

            # อัปโหลดภาพไปที่ Firebase Storage
            bucket = storage.bucket()
            image_path = f'Images/{room_number}.png'  # ใช้ Room_Number เป็นชื่อไฟล์
            blob = bucket.blob(image_path)
            blob.upload_from_file(image_io, content_type='image/png')

        # เพิ่มข้อมูลลง Firebase **โดยไม่เพิ่ม image_url**
        ref = db.reference(f'room/{room_number}')
        ref.set(data)

        return jsonify({'message': 'User added successfully', 'room_number': room_number, 'last_attendance_time': data['last_attendance_time']}), 201

    except Exception as e:
        print(f"Error adding user: {e}")
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/upload-face-images', methods=['POST'])
def upload_face_images():
    try:
        # รับค่า Room_Number และรายการไฟล์ที่อัปโหลด
        room_number = request.form.get('Room_Number')
        face_images = request.files.getlist('faceImages')

        if not room_number or not face_images:
            return jsonify({'error': 'Missing Room Number or face images'}), 400

        # กำหนดโฟลเดอร์ที่ใช้เก็บรูปภาพใน Firebase Storage
        folder_path = f'trainface/{room_number}/'
        bucket = storage.bucket()

        uploaded_files = []
        for idx, face_image in enumerate(face_images):
            # อ่านไฟล์และเตรียมอัปโหลด
            face_io = io.BytesIO(face_image.read())
            face_path = f'{folder_path}face_{idx}.png'
            blob = bucket.blob(face_path)

            # ✅ อัปโหลดไฟล์ไปยัง Firebase Storage
            blob.upload_from_file(io.BytesIO(face_io.getvalue()), content_type='image/png')

            # 🔹 บันทึก URL ของไฟล์ที่อัปโหลดสำเร็จ
            uploaded_files.append(blob.public_url)

        return jsonify({
            'message': 'Face images uploaded successfully',
            'room_number': room_number,
            'uploaded_files': uploaded_files
        }), 201

    except Exception as e:
        print(f"Error uploading face images: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
