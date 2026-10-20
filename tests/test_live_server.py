import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import re
from modules.db import get_user_by_whatsapp, delete_user

s = requests.Session()
r = s.get('http://127.0.0.1:5000/register', timeout=5)
print('GET /register status:', r.status_code)

m = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text)
token = m.group(1) if m else ''
print('CSRF token found:', bool(token))

# Clean up before
u = get_user_by_whatsapp('+919999900000')
if u:
    delete_user(u['id'])

p = s.post('http://127.0.0.1:5000/register', data={
    'csrf_token': token,
    'name': 'Live Test User',
    'whatsapp': '+919999900000',
    'password': 'Password123!',
    'confirm_password': 'Password123!',
    'delivery_time': '08:00',
    'timezone': 'Asia/Kolkata'
}, allow_redirects=True, timeout=5)

print('POST response URL:', p.url, '| status:', p.status_code)
if 'Server error' in p.text or 'Error 500' in p.text:
    print('[FAIL] Live server gave 500 Error!')
else:
    print('[SUCCESS] Live server registered user successfully!')

# Clean up after
u = get_user_by_whatsapp('+919999900000')
if u:
    delete_user(u['id'])
    print('Cleaned up test user.')
