from flask import Flask, request, jsonify, send_from_directory,render_template
from flask_cors import CORS
from datetime import datetime, timedelta
import os
import re

from database import db, Teacher, Student, Attendance, Lesson, Session
from author import hash_password, verify_password, login_required, verify_token, generate_token

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=BASE_DIR, static_url_path='')
CORS(app, supports_credentials=True, origins=['*'])

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'musicspot.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'

db.init_app(app)

# Create tables
with app.app_context():
    db.create_all()
    
    if not Teacher.query.filter_by(email='jaimit@musicspot.com').first():
        jaimit = Teacher(
            email='jaimit@musicspot.com',
            name='Jaimit Sir',
            password_hash=hash_password('studio123'),
            instrument='both'
        )
        db.session.add(jaimit)
        print("✅ Created Jaimit Sir account (Keyboard + Guitar)")
    
    if not Teacher.query.filter_by(email='jay@musicspot.com').first():
        jay = Teacher(
            email='jay@musicspot.com',
            name='Jay Sir',
            password_hash=hash_password('studio123'),
            instrument='guitar'
        )
        db.session.add(jay)
        print("✅ Created Jay Sir account (Guitar only)")
    
    db.session.commit()
    print("✅ Database initialized")

# ============ FRONTEND ============
@app.route('/')
def serve_frontend():
    return render_template('frontend.html')
# ============ AUTHENTICATION API ============
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    remember_me = data.get('rememberMe', False)
    
    teacher = Teacher.query.filter_by(email=email).first()
    
    if not teacher or not verify_password(password, teacher.password_hash):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    token = generate_token(teacher.id, remember_me)
    
    response = jsonify({
        'success': True,
        'token': token,
        'teacher': {
            'id': teacher.id,
            'name': teacher.name,
            'email': teacher.email,
            'instrument': teacher.instrument
        },
        'rememberMe': remember_me
    })
    
    response.set_cookie('token', token, httponly=True, max_age=30*24*3600 if remember_me else 24*3600)
    return response

@app.route('/api/logout', methods=['POST'])
def api_logout():
    token = request.cookies.get('token') or request.headers.get('Authorization', '').replace('Bearer ', '')
    if token:
        Session.query.filter_by(token=token).delete()
        db.session.commit()
    
    response = jsonify({'success': True})
    response.set_cookie('token', '', expires=0)
    return response

@app.route('/api/verify', methods=['GET'])
def api_verify():
    token = request.cookies.get('token') or request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'authenticated': False}), 401
    
    teacher_id = verify_token(token)
    if not teacher_id:
        return jsonify({'authenticated': False}), 401
    
    teacher = Teacher.query.get(teacher_id)
    return jsonify({
        'authenticated': True,
        'teacher': {
            'id': teacher.id,
            'name': teacher.name,
            'email': teacher.email,
            'instrument': teacher.instrument
        }
    })

# ============ PROFILE MANAGEMENT API ============
@app.route('/api/profile', methods=['GET'])
@login_required
def api_get_profile():
    teacher = Teacher.query.get(request.teacher_id)
    if not teacher:
        return jsonify({'error': 'Teacher not found'}), 404
    
    return jsonify({
        'success': True,
        'profile': {
            'id': teacher.id,
            'name': teacher.name,
            'email': teacher.email,
            'instrument': teacher.instrument,
            'phone': teacher.phone,
            'address': teacher.address,
            'profile_pic': teacher.profile_pic,
            'created_at': teacher.created_at.isoformat(),
            'last_login': teacher.last_login.isoformat() if teacher.last_login else None
        }
    })

@app.route('/api/profile', methods=['PUT'])
@login_required
def api_update_profile():
    teacher = Teacher.query.get(request.teacher_id)
    if not teacher:
        return jsonify({'error': 'Teacher not found'}), 404
    
    data = request.json
    
    if 'name' in data:
        teacher.name = data['name']
    if 'phone' in data:
        teacher.phone = data['phone']
    if 'address' in data:
        teacher.address = data['address']
    if 'profile_pic' in data:
        teacher.profile_pic = data['profile_pic']
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Profile updated successfully',
        'profile': {
            'id': teacher.id,
            'name': teacher.name,
            'email': teacher.email,
            'instrument': teacher.instrument,
            'phone': teacher.phone,
            'address': teacher.address
        }
    })

@app.route('/api/change-password', methods=['POST'])
@login_required
def api_change_password():
    teacher = Teacher.query.get(request.teacher_id)
    if not teacher:
        return jsonify({'error': 'Teacher not found'}), 404
    
    data = request.json
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')
    
    if not current_password or not new_password or not confirm_password:
        return jsonify({'error': 'All password fields are required'}), 400
    
    if new_password != confirm_password:
        return jsonify({'error': 'New passwords do not match'}), 400
    
    if len(new_password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    
    if not verify_password(current_password, teacher.password_hash):
        return jsonify({'error': 'Current password is incorrect'}), 401
    
    teacher.password_hash = hash_password(new_password)
    db.session.commit()
    
    Session.query.filter_by(teacher_id=teacher.id).delete()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Password changed successfully. Please login again.'
    })

@app.route('/api/update-last-login', methods=['POST'])
@login_required
def api_update_last_login():
    teacher = Teacher.query.get(request.teacher_id)
    if teacher:
        teacher.last_login = datetime.now()
        db.session.commit()
    return jsonify({'success': True})

# ============ STUDENT MANAGEMENT API ============
@app.route('/api/students', methods=['GET'])
@login_required
def api_get_students():
    students = Student.query.filter_by(teacher_id=request.teacher_id).order_by(Student.created_at.desc()).all()
    
    result = []
    for student in students:
        current_month = datetime.now().month
        current_year = datetime.now().year
        
        attendance_this_month = Attendance.query.filter(
            Attendance.student_id == student.id,
            Attendance.date >= datetime(current_year, current_month, 1),
            Attendance.status == True
        ).count()
        
        if student.fee_plan == '12days':
            total_days_needed = 12
        elif student.fee_plan == '8days':
            total_days_needed = 8
        elif student.fee_plan == '3months':
            total_days_needed = 36
        else:
            total_days_needed = 12
        
        result.append({
            'id': student.id,
            'name': student.name,
            'contact': student.contact,
            'course': student.course,
            'parentContact': student.parent_contact,
            'feePlan': student.fee_plan,
            'feeStatus': student.fee_status,
            'feeAmount': student.fee_amount,
            'lastPaymentDate': student.last_payment_date.isoformat() if student.last_payment_date else None,
            'notes': student.notes,
            'progress': student.progress,
            'attendanceThisMonth': attendance_this_month,
            'totalDaysNeeded': total_days_needed,
            'remainingDays': total_days_needed - attendance_this_month,
            'attendancePercentage': round((attendance_this_month / total_days_needed * 100), 2) if total_days_needed > 0 else 0
        })
    
    return jsonify({
        'success': True,
        'count': len(result),
        'students': result
    })

@app.route('/api/students', methods=['POST'])
@login_required
def api_create_student():
    try:
        data = request.json
        teacher = Teacher.query.get(request.teacher_id)
        
        fee_amount = data.get('feeAmount', 0)
        if fee_amount == 0:
            if data.get('feePlan') == '12days':
                fee_amount = 3000
            elif data.get('feePlan') == '8days':
                fee_amount = 2200
            elif data.get('feePlan') == '3months':
                fee_amount = 7500
        
        student = Student(
            teacher_id=request.teacher_id,
            name=data['name'],
            contact=data['contact'],
            course=data['course'],
            parent_contact=data.get('parentContact'),
            fee_plan=data.get('feePlan', '12days'),
            notes=data.get('notes'),
            progress=data.get('progress'),
            fee_amount=fee_amount,
            fee_status='unpaid'
        )
        
        db.session.add(student)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{student.name} added successfully',
            'student': {
                'id': student.id,
                'name': student.name,
                'feeAmount': student.fee_amount,
                'feePlan': student.fee_plan
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/students/<int:student_id>', methods=['DELETE'])
@login_required
def api_delete_student(student_id):
    student = Student.query.filter_by(id=student_id, teacher_id=request.teacher_id).first()
    if not student:
        return jsonify({'error': 'Student not found'}), 404
    
    db.session.delete(student)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'{student.name} deleted'})

@app.route('/api/students/<int:student_id>/payment', methods=['PATCH'])
@login_required
def api_update_payment(student_id):
    student = Student.query.filter_by(id=student_id, teacher_id=request.teacher_id).first()
    if not student:
        return jsonify({'error': 'Student not found'}), 404
    
    data = request.json
    student.fee_status = data.get('feeStatus', student.fee_status)
    
    if data.get('feeStatus') == 'paid':
        student.last_payment_date = datetime.now().date()
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Payment marked as {student.fee_status}',
        'studentId': student_id,
        'feeStatus': student.fee_status
    })

# ============ ATTENDANCE API ============
@app.route('/api/attendance/calendar/<int:student_id>', methods=['GET'])
@login_required
def api_get_attendance_calendar(student_id):
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    student = Student.query.filter_by(id=student_id, teacher_id=request.teacher_id).first()
    if not student:
        return jsonify({'error': 'Student not found'}), 404
    
    start_date = datetime(year, month, 1).date()
    if month == 12:
        end_date = datetime(year+1, 1, 1).date() - timedelta(days=1)
    else:
        end_date = datetime(year, month+1, 1).date() - timedelta(days=1)
    
    attendance_records = Attendance.query.filter(
        Attendance.student_id == student_id,
        Attendance.date >= start_date,
        Attendance.date <= end_date
    ).all()
    
    calendar_data = {}
    for record in attendance_records:
        calendar_data[record.date.day] = {
            'status': record.status,
            'date': record.date.isoformat()
        }
    
    days_present = sum(1 for r in attendance_records if r.status)
    
    if student.fee_plan == '12days':
        total_required = 12
        fee_text = "₹3,000/month"
    elif student.fee_plan == '8days':
        total_required = 8
        fee_text = "₹2,200/month"
    elif student.fee_plan == '3months':
        total_required = 36
        fee_text = "₹7,500 for 3 months"
    else:
        total_required = 12
        fee_text = "₹3,000/month"
    
    return jsonify({
        'success': True,
        'studentId': student_id,
        'studentName': student.name,
        'year': year,
        'month': month,
        'monthName': datetime(year, month, 1).strftime('%B'),
        'feePlan': student.fee_plan,
        'feeAmount': student.fee_amount,
        'feeText': fee_text,
        'feeStatus': student.fee_status,
        'daysPresent': days_present,
        'totalRequired': total_required,
        'daysRemaining': total_required - days_present,
        'sessionCompleted': days_present >= total_required,
        'attendancePercentage': round((days_present / total_required * 100), 2) if total_required > 0 else 0,
        'calendar': calendar_data
    })

@app.route('/api/attendance/mark', methods=['POST'])
@login_required
def api_mark_attendance():
    data = request.json
    student_id = data.get('studentId')
    date_str = data.get('date')
    status = data.get('status', True)
    
    if not student_id or not date_str:
        return jsonify({'error': 'studentId and date are required'}), 400
    
    student = Student.query.filter_by(id=student_id, teacher_id=request.teacher_id).first()
    if not student:
        return jsonify({'error': 'Student not found'}), 404
    
    date = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    attendance = Attendance.query.filter_by(student_id=student_id, date=date).first()
    if attendance:
        attendance.status = status
        message = 'Attendance updated'
    else:
        attendance = Attendance(student_id=student_id, date=date, status=status)
        db.session.add(attendance)
        message = 'Attendance marked'
    
    db.session.commit()
    
    current_month = datetime.now().month
    current_year = datetime.now().year
    days_present = Attendance.query.filter(
        Attendance.student_id == student_id,
        Attendance.date >= datetime(current_year, current_month, 1),
        Attendance.status == True
    ).count()
    
    if student.fee_plan == '12days':
        total_required = 12
    elif student.fee_plan == '8days':
        total_required = 8
    elif student.fee_plan == '3months':
        total_required = 36
    else:
        total_required = 12
    
    session_completed = days_present >= total_required
    remaining = total_required - days_present
    
    alert_message = None
    if session_completed and remaining == 0:
        alert_message = f"🎉 {student.name} has completed {days_present}/{total_required} classes! New session starts from tomorrow."
    
    return jsonify({
        'success': True,
        'message': message,
        'studentId': student_id,
        'studentName': student.name,
        'date': date_str,
        'status': status,
        'daysPresent': days_present,
        'totalRequired': total_required,
        'remaining': remaining,
        'sessionCompleted': session_completed,
        'attendancePercentage': round((days_present / total_required * 100), 2) if total_required > 0 else 0,
        'alert': alert_message
    })

@app.route('/api/attendance/today', methods=['GET'])
@login_required
def api_get_today_attendance():
    today = datetime.now().date()
    students = Student.query.filter_by(teacher_id=request.teacher_id).all()
    
    result = []
    for student in students:
        attendance = Attendance.query.filter_by(student_id=student.id, date=today).first()
        
        current_month = datetime.now().month
        current_year = datetime.now().year
        days_present = Attendance.query.filter(
            Attendance.student_id == student.id,
            Attendance.date >= datetime(current_year, current_month, 1),
            Attendance.status == True
        ).count()
        
        if student.fee_plan == '12days':
            total_required = 12
        elif student.fee_plan == '8days':
            total_required = 8
        elif student.fee_plan == '3months':
            total_required = 36
        else:
            total_required = 12
        
        result.append({
            'id': student.id,
            'name': student.name,
            'course': student.course,
            'feePlan': student.fee_plan,
            'feeStatus': student.fee_status,
            'attendedToday': attendance.status if attendance else False,
            'daysPresent': days_present,
            'totalRequired': total_required,
            'progress': f"{days_present}/{total_required}",
            'remaining': total_required - days_present,
            'completed': days_present >= total_required
        })
    
    return jsonify({
        'success': True,
        'date': today.isoformat(),
        'dayName': today.strftime('%A'),
        'students': result
    })

# ============ PAYMENTS API ============
@app.route('/api/payments/unpaid', methods=['GET'])
@login_required
def api_get_unpaid_students():
    students = Student.query.filter_by(
        teacher_id=request.teacher_id,
        fee_status='unpaid'
    ).all()
    
    result = [{
        'id': s.id,
        'name': s.name,
        'contact': s.contact,
        'parentContact': s.parent_contact,
        'course': s.course,
        'feeAmount': s.fee_amount,
        'feePlan': s.fee_plan
    } for s in students]
    
    return jsonify({
        'success': True,
        'count': len(result),
        'unpaidStudents': result
    })

# ============ WHATSAPP API ============
@app.route('/api/whatsapp/reminder', methods=['POST'])
@login_required
def api_send_whatsapp_reminder():
    data = request.json
    student_id = data.get('studentId')
    reminder_type = data.get('type', 'payment')
    
    student = Student.query.filter_by(id=student_id, teacher_id=request.teacher_id).first()
    if not student:
        return jsonify({'error': 'Student not found'}), 404
    
    teacher = Teacher.query.get(request.teacher_id)
    
    current_month = datetime.now().month
    current_year = datetime.now().year
    days_present = Attendance.query.filter(
        Attendance.student_id == student_id,
        Attendance.date >= datetime(current_year, current_month, 1),
        Attendance.status == True
    ).count()
    
    if student.fee_plan == '12days':
        total_required = 12
        plan_text = "12 days per month"
        plan_emoji = "📅"
    elif student.fee_plan == '8days':
        total_required = 8
        plan_text = "8 days per month"
        plan_emoji = "📆"
    elif student.fee_plan == '3months':
        total_required = 36
        plan_text = "36 classes over 3 months"
        plan_emoji = "🎯"
    else:
        total_required = 12
        plan_text = "12 days per month"
        plan_emoji = "📅"
    
    if reminder_type == 'payment':
        message = f"""📢 *🎵 MusicSpot Studio - Payment Reminder* 🎵

Dear Parent/Guardian of *{student.name}*,

This is a gentle reminder that the tuition fees for *{student.course}* lessons are pending.

{plan_emoji} *Fee Plan:* {plan_text}
💰 *Amount Due:* ₹{student.fee_amount}
👨‍🏫 *Teacher:* {teacher.name}
📱 *Contact:* {teacher.phone if teacher.phone else 'Not provided'}

Please clear the dues at your earliest convenience to ensure uninterrupted classes.

Thank you for your cooperation! 🙏

*Regards,*
{teacher.name}
🎵 MusicSpot Studio
━━━━━━━━━━━━━━━━━━━━━"""
    
    elif reminder_type == 'attendance':
        remaining = total_required - days_present
        percentage = (days_present / total_required * 100) if total_required > 0 else 0
        
        progress_bar = ""
        filled = int(percentage / 10)
        for i in range(10):
            if i < filled:
                progress_bar += "█"
            else:
                progress_bar += "░"
        
        message = f"""📢 *🎵 MusicSpot Studio - Attendance Update* 🎵

Dear Parent/Guardian of *{student.name}*,

Here's the attendance progress for this session:

{progress_bar} {percentage:.0f}%

📊 *Progress:* {days_present} out of {total_required} classes completed
📈 *Remaining:* {remaining} classes
{plan_emoji} *Plan:* {plan_text}
🎸 *Course:* {student.course}
👨‍🏫 *Teacher:* {teacher.name}

Please ensure regular attendance for better learning outcomes! 🌟

*Regards,*
{teacher.name}
🎵 MusicSpot Studio
━━━━━━━━━━━━━━━━━━━━━"""
    
    elif reminder_type == 'completion':
        message = f"""🎉 *🎵 MusicSpot Studio - Session Completed!* 🎉🎊

Dear Parent/Guardian of *{student.name}*,

🎯 *CONGRATULATIONS!* 🎯

Your child has successfully completed {days_present}/{total_required} classes for this session!

📅 *Plan:* {plan_text}
🎸 *Course:* {student.course}
👨‍🏫 *Teacher:* {teacher.name}
⭐ *Performance:* Excellent!

A new session starts from tomorrow. Please contact us to renew the subscription.

Thank you for choosing MusicSpot Studio! 🙏

*Regards,*
{teacher.name}
🎵 MusicSpot Studio
━━━━━━━━━━━━━━━━━━━━━"""
    
    else:
        message = f"""📢 *🎵 MusicSpot Studio Update* 🎵

Dear Parent/Guardian of {student.name},

This is an update regarding {student.course} lessons at MusicSpot Studio.

👨‍🏫 *Teacher:* {teacher.name}

Please contact the studio for more information.

*Regards,*
{teacher.name}
🎵 MusicSpot Studio
━━━━━━━━━━━━━━━━━━━━━"""
    
    phone = re.sub(r'\D', '', student.parent_contact if student.parent_contact else student.contact)
    encoded_message = message.replace('\n', '%0A').replace(' ', '%20').replace('*', '%2A')
    
    whatsapp_url = f"https://wa.me/{phone}?text={encoded_message}" if phone else f"https://web.whatsapp.com/send?text={encoded_message}"
    
    return jsonify({
        'success': True,
        'whatsappUrl': whatsapp_url,
        'message': message,
        'phone': phone if phone else None,
        'teacherName': teacher.name
    })

# ============ STATISTICS API (FIXED - ONLY ONE VERSION) ============
@app.route('/api/stats', methods=['GET'])
@login_required
def api_get_stats():
    total_students = Student.query.filter_by(teacher_id=request.teacher_id).count()
    unpaid_students = Student.query.filter_by(teacher_id=request.teacher_id, fee_status='unpaid').count()
    
    paid_students = Student.query.filter_by(teacher_id=request.teacher_id, fee_status='paid').all()
    total_revenue = sum(s.fee_amount for s in paid_students)
    
    # Get students who have completed their sessions
    current_month = datetime.now().month
    current_year = datetime.now().year
    
    students = Student.query.filter_by(teacher_id=request.teacher_id).all()
    completed_sessions = 0
    for student in students:
        days_present = Attendance.query.filter(
            Attendance.student_id == student.id,
            Attendance.date >= datetime(current_year, current_month, 1),
            Attendance.status == True
        ).count()
        
        if student.fee_plan == '12days':
            total_required = 12
        elif student.fee_plan == '8days':
            total_required = 8
        elif student.fee_plan == '3months':
            total_required = 36
        else:
            total_required = 12
        
        if days_present >= total_required:
            completed_sessions += 1
    
    return jsonify({
        'success': True,
        'stats': {
            'totalStudents': total_students,
            'unpaidStudents': unpaid_students,
            'totalRevenue': total_revenue,
            'completedSessions': completed_sessions
        }
    })

if __name__ == '__main__':
    print("=" * 60)
    print("🎵 MusicSpot Studio Management System")
    print("=" * 60)
    print(f"🌐 Server: http://localhost:3000")
    print("\n📧 Login Credentials:")
    print("   Jaimit Sir: jaimit@musicspot.com / studio123 (Keyboard + Guitar)")
    print("   Jay Sir:    jay@musicspot.com / studio123 (Guitar only)")
    print("=" * 60)
    app.run(debug=True, port=3000, host='0.0.0.0')
