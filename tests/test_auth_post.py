import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from modules.db import init_db, get_user_by_whatsapp, delete_user

init_db()

with app.test_client() as client:
    # 1. Get CSRF token from /register
    get_res = client.get('/register')
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', get_res.text)
    csrf_token = m.group(1) if m else ''
    assert csrf_token, "No CSRF token found in /register"

    # Clean existing
    u = get_user_by_whatsapp('+919876543210')
    if u:
        delete_user(u['id'])

    # 2. Post registration
    post_res = client.post('/register', data={
        'csrf_token': csrf_token,
        'name': 'Srishti Singh',
        'whatsapp': '+919876543210',
        'password': 'Password123!',
        'confirm_password': 'Password123!',
        'delivery_time': '08:00',
        'timezone': 'Asia/Kolkata'
    }, follow_redirects=True)

    print('POST /register status code:', post_res.status_code)
    assert post_res.status_code == 200
    assert 'Welcome, Srishti Singh!' in post_res.text or 'Dashboard' in post_res.text
    print('[OK] Registration form submitted successfully and opened dashboard!')

    # 3. Test login
    get_login = client.get('/login')
    m_login = re.search(r'name="csrf_token"\s+value="([^"]+)"', get_login.text)
    login_csrf = m_login.group(1) if m_login else ''

    post_login = client.post('/login', data={
        'csrf_token': login_csrf,
        'whatsapp': '+919876543210',
        'password': 'Password123!'
    }, follow_redirects=True)

    print('POST /login status code:', post_login.status_code)
    assert post_login.status_code == 200
    assert 'Welcome back, Srishti Singh!' in post_login.text or 'Dashboard' in post_login.text
    print('[OK] Login form submitted successfully and opened dashboard!')

    # 4. Clean up
    u_after = get_user_by_whatsapp('+919876543210')
    if u_after:
        delete_user(u_after['id'])

print('\n=== ALL REGISTRATION AND LOGIN WORKFLOWS VERIFIED (ZERO 500 ERRORS) ===')

