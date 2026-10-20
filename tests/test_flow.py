"""
Integration test suite for Inbox Insights.
"""
import os
import sys
import secrets
from datetime import datetime, timezone, timedelta

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from werkzeug.security import generate_password_hash
from app import app
from modules.db import (
    init_db, create_user, get_user_by_whatsapp, add_gmail_account,
    create_report, get_reports, delete_user
)
from modules.crypto import encrypt_token, decrypt_token


def run_tests():
    init_db()

    # 1. Crypto test
    raw_token = '{"token": "ya29.test12345"}'
    enc = encrypt_token(raw_token)
    dec = decrypt_token(enc)
    assert dec == raw_token, 'Crypto mismatch!'
    print('[OK] Token encryption & decryption')

    # 2. User CRUD
    phone = '+919999988888'
    existing = get_user_by_whatsapp(phone)
    if existing:
        delete_user(existing['id'])

    uid = create_user('Srishti Test', phone, generate_password_hash('SecretPass123!'), '08:00', 'Asia/Kolkata')
    assert uid > 0
    print(f'[OK] User created with ID: {uid}')

    # 3. Add Gmail Account
    acc_id = add_gmail_account(uid, 'College Gmail', 'student@college.edu', enc)
    assert acc_id > 0
    print(f'[OK] Gmail account added with ID: {acc_id}')

    # 4. Create dummy report & signed link
    token = secrets.token_hex(32)
    exp = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
    rep_id = create_report(uid, '2026-10-20', 5, 2, 'output/test_report.pdf', token, exp)
    print(f'[OK] Report created with ID: {rep_id}')

    # 5. Test client dashboard & signed link
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = uid

        dash_res = client.get('/dashboard')
        assert dash_res.status_code == 200, f'Dashboard failed with {dash_res.status_code}'
        assert b'Good ' in dash_res.data
        assert b'College Gmail' in dash_res.data
        assert b'student@college.edu' in dash_res.data
        print('[OK] Dashboard rendered with accounts and stats!')

        link_res = client.get(f'/r/{token}')
        assert link_res.status_code == 200, f'PDF link returned {link_res.status_code}'
        assert link_res.mimetype == 'application/pdf'
        print('[OK] Signed PDF link /r/<token> served correctly (200 application/pdf)!')

    # Cleanup test user
    delete_user(uid)
    print('[OK] Cleanup completed successfully.')

    print('\n=========================================')
    print(' ALL INBOX INSIGHTS INTEGRATION TESTS PASSED!')
    print('=========================================')


if __name__ == '__main__':
    run_tests()
