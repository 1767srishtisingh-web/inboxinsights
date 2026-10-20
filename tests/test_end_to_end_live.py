import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import re
from modules.db import get_user_by_whatsapp, delete_user, add_gmail_account, create_report
from modules.crypto import encrypt_token
import secrets
from datetime import datetime, timezone, timedelta

s = requests.Session()

# 1. Register test user
reg_get = s.get('http://127.0.0.1:5000/register', timeout=5)
assert reg_get.status_code == 200, f'GET /register failed: {reg_get.status_code}'
m = re.search(r'name="csrf_token"\s+value="([^"]+)"', reg_get.text)
csrf_token = m.group(1) if m else ''
assert csrf_token, 'No CSRF token found in registration form'

phone = '+919999911111'
u = get_user_by_whatsapp(phone)
if u:
    delete_user(u['id'])

reg_post = s.post('http://127.0.0.1:5000/register', data={
    'csrf_token': csrf_token,
    'name': 'Srishti Singh',
    'whatsapp': phone,
    'password': 'Password123!',
    'confirm_password': 'Password123!',
    'delivery_time': '09:00',
    'timezone': 'Asia/Kolkata'
}, allow_redirects=True, timeout=5)

assert reg_post.status_code == 200, f'POST /register failed: {reg_post.status_code}'
assert 'dashboard' in reg_post.url.lower(), f'Did not redirect to dashboard, url is: {reg_post.url}'
assert 'Srishti' in reg_post.text, 'User name not rendered on dashboard'
print('[PASS] Step 1: Registration completed & redirected to Dashboard (HTTP 200)')

# 2. Verify user in DB
created_user = get_user_by_whatsapp(phone)
assert created_user is not None, 'User record not found in database!'
uid = created_user['id']
print(f'[PASS] Step 2: User successfully written to SQLite database (User ID: {uid})')

# 3. Add simulated connected Gmail account
enc_token = encrypt_token('{"access_token": "mock_token"}')
acc_id = add_gmail_account(uid, 'Work Gmail', 'srishti.singh@example.com', enc_token)
print(f'[PASS] Step 3: Connected Gmail account saved to database (Account ID: {acc_id})')

# 4. Refresh Dashboard to verify accounts list
dash_res = s.get('http://127.0.0.1:5000/dashboard', timeout=5)
assert dash_res.status_code == 200
assert 'srishti.singh@example.com' in dash_res.text
assert 'Work Gmail' in dash_res.text
print('[PASS] Step 4: Dashboard displays connected inboxes list properly')

# 5. Update delivery settings via live POST
dash_csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', dash_res.text).group(1)
settings_post = s.post('http://127.0.0.1:5000/settings/delivery', data={
    'csrf_token': dash_csrf,
    'delivery_time': '10:30',
    'timezone': 'Asia/Kolkata',
    'delivery_enabled': 'on'
}, allow_redirects=True, timeout=5)
assert settings_post.status_code == 200
updated_user = get_user_by_whatsapp(phone)
assert updated_user['delivery_time'] == '10:30'
print('[PASS] Step 5: Delivery settings updated to 10:30 (HTTP 200)')

# 6. Create report & test signed PDF download via /r/<token>
token = secrets.token_hex(32)
exp = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
from modules.pdf_generator import generate_pdf
pdf_path = f'output/report_{uid}_2026-10-21.pdf'
generate_pdf('Srishti Singh', '2026-10-21', [
    {'subject': 'Project Deliverable submission reminder', 'deadline': '25 Oct 2026, 5:00 PM – submit deliverable'},
    {'subject': 'Team Standup notes', 'deadline': None}
], pdf_path)
rep_id = create_report(uid, '2026-10-21', 2, 1, pdf_path, token, exp)

pdf_res = s.get(f'http://127.0.0.1:5000/r/{token}', timeout=5)
assert pdf_res.status_code == 200
assert pdf_res.headers.get('content-type') == 'application/pdf'
assert len(pdf_res.content) > 1000
print(f'[PASS] Step 6: Signed PDF served at /r/{token} (HTTP 200, {len(pdf_res.content)} bytes PDF)')

# Clean up
delete_user(uid)
print('\n======================================================')
print(' ALL LIVE SERVER WORKFLOW TESTS PASSED WITHOUT ERRORS!')
print('======================================================')

