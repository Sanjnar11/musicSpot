import bcrypt
import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify
from database import db, Session

JWT_SECRET = 'musicspot_super_secret_key_change_this_in_production'
JWT_ALGORITHM = 'HS256'

def hash_password(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password, password_hash):
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

def generate_token(teacher_id, remember_me=False):
    expires_delta = timedelta(days=30 if remember_me else 1)
    expires_at = datetime.utcnow() + expires_delta
    
    payload = {
        'teacher_id': teacher_id,
        'exp': expires_at
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    session = Session(
        teacher_id=teacher_id,
        token=token,
        expires_at=expires_at
    )
    db.session.add(session)
    db.session.commit()
    
    return token

def verify_token(token):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        session = Session.query.filter_by(token=token).first()
        if session and session.expires_at > datetime.utcnow():
            return payload['teacher_id']
        return None
    except:
        return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.cookies.get('token') or request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if not token:
            return jsonify({'error': 'Authentication required'}), 401
        
        teacher_id = verify_token(token)
        if not teacher_id:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        request.teacher_id = teacher_id
        return f(*args, **kwargs)
    
    return decorated_function