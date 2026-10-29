"""Quotation-related API routes."""
from datetime import datetime
from html import escape as html_escape
from flask import Blueprint, request, jsonify, session
from utils import send_email

# Create Blueprint for quotation routes
quotation_bp = Blueprint('quotation', __name__)

# Simple in-process rate limit: dockey -> last sent unix time (per process).
_EMAIL_NOTIFY_LAST_SENT: dict[str, float] = {}
_EMAIL_NOTIFY_COOLDOWN_SECONDS = 60.0


def _html(value) -> str:
    return html_escape(str(value if value is not None else ''), quote=True)


@quotation_bp.route('/api/send_quotation_email', methods=['POST'])
def send_quotation_email():
    """Send quotation pending email using server-side quotation data only."""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    user_email = (session.get('user_email') or '').strip()
    data = request.get_json() or {}
    try:
        dockey = int(data.get('dockey') or 0)
    except (TypeError, ValueError):
        dockey = 0
    if dockey <= 0:
        return jsonify({'success': False, 'error': 'dockey is required'}), 400

    # Rate-limit duplicate notifications for the same document.
    import time as _time
    rate_key = f"{session.get('customer_code') or user_email}:{dockey}"
    now = _time.time()
    last = float(_EMAIL_NOTIFY_LAST_SENT.get(rate_key) or 0)
    if last and (now - last) < _EMAIL_NOTIFY_COOLDOWN_SECONDS:
        return jsonify({
            'success': True,
            'message': 'Notification already sent recently',
            'deduped': True,
        })

    try:
        from utils.quotation_api import fetch_quotation_details_for_email

        qt = fetch_quotation_details_for_email(dockey)
        if not qt.get('success') or not isinstance(qt.get('data'), dict):
            return jsonify({'success': False, 'error': 'Quotation not found'}), 404

        row = qt['data']
        qt_code = str(row.get('CODE') or row.get('code') or '').strip()
        qt_company = str(row.get('COMPANYNAME') or row.get('companyName') or '').strip()

        # Ownership: require matching customer CODE (admins may notify any QT).
        if session.get('user_type') != 'admin':
            sess_code = str(session.get('customer_code') or '').strip().upper()
            if not sess_code or sess_code != qt_code.upper():
                return jsonify({'success': False, 'error': 'Forbidden'}), 403

        docno = str(row.get('DOCNO') or row.get('docno') or '').strip() or 'N/A'
        company_name = qt_company or 'Valued Customer'
        try:
            total_amount = float(row.get('DOCAMT') or row.get('docamt') or 0)
        except (TypeError, ValueError):
            total_amount = 0.0
        items = row.get('items') or row.get('DETAILS') or row.get('details') or []
        if not isinstance(items, list):
            items = []

        items_html = ''
        for idx, item in enumerate(items, 1):
            if not isinstance(item, dict):
                continue
            product = (
                item.get('DESCRIPTION')
                or item.get('description')
                or item.get('product')
                or item.get('ITEMCODE')
                or ''
            )
            try:
                qty = float(item.get('QTY') or item.get('qty') or 0)
            except (TypeError, ValueError):
                qty = 0.0
            try:
                price = float(item.get('UNITPRICE') or item.get('unitPrice') or item.get('price') or 0)
            except (TypeError, ValueError):
                price = 0.0
            try:
                discount = float(item.get('DISC') or item.get('discount') or 0)
            except (TypeError, ValueError):
                discount = 0.0
            subtotal = (qty * price) - discount
            items_html += f'''
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #e0e0e0;">{idx}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e0e0e0;">{_html(product)}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e0e0e0; text-align: center;">{_html(f"{qty:g}")}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e0e0e0; text-align: right;">RM {_html(f"{price:.2f}")}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e0e0e0; text-align: right;">RM {_html(f"{discount:.2f}")}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e0e0e0; text-align: right;">RM {_html(f"{subtotal:.2f}")}</td>
            </tr>
            '''

        subject = f"Quotation {_html(docno)} - Pending Approval".replace('&amp;', '&')
        # Subject should not contain HTML entities — use plain docno.
        subject = f"Quotation {docno} - Pending Approval"
        body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9; border-radius: 8px;">
                    <div style="background-color: #1a1f2e; color: #fff; padding: 20px; border-radius: 8px 8px 0 0; text-align: center;">
                        <h1 style="margin: 0;">Quotation Pending Approval</h1>
                    </div>

                    <div style="background-color: #fff; padding: 30px; border-radius: 0 0 8px 8px;">
                        <p style="font-size: 16px;">Dear {_html(company_name)},</p>

                        <p>Thank you for your request. Your quotation has been created and is currently pending approval.</p>

                        <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                            <p style="margin: 5px 0;"><strong>Quotation Number:</strong> {_html(docno)}</p>
                            <p style="margin: 5px 0;"><strong>Date:</strong> {_html(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}</p>
                        </div>

                        <h3 style="color: #1a1f2e; border-bottom: 2px solid #1a1f2e; padding-bottom: 10px;">Quotation Details</h3>

                        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                            <thead>
                                <tr style="background-color: #1a1f2e; color: #fff;">
                                    <th style="padding: 10px; text-align: left;">#</th>
                                    <th style="padding: 10px; text-align: left;">Product</th>
                                    <th style="padding: 10px; text-align: center;">Qty</th>
                                    <th style="padding: 10px; text-align: right;">Unit Price</th>
                                    <th style="padding: 10px; text-align: right;">Discount</th>
                                    <th style="padding: 10px; text-align: right;">Subtotal</th>
                                </tr>
                            </thead>
                            <tbody>
                                {items_html}
                            </tbody>
                            <tfoot>
                                <tr style="background-color: #f5f5f5; font-weight: bold;">
                                    <td colspan="5" style="padding: 15px; text-align: right;">Total Amount:</td>
                                    <td style="padding: 15px; text-align: right;">RM {_html(f"{total_amount:.2f}")}</td>
                                </tr>
                            </tfoot>
                        </table>

                        <div style="background-color: #fff8e1; padding: 15px; border-left: 4px solid #f0ad4e; margin: 20px 0;">
                            <p style="margin: 0;"><strong>Next Steps:</strong></p>
                            <p style="margin: 10px 0 0 0;">Your quotation is awaiting approval. You can check its status from your quotation page.</p>
                        </div>

                        <p style="margin-top: 30px;">If you have any questions about this quotation, please don't hesitate to contact us.</p>

                        <p style="margin-top: 20px;">Best regards,<br><strong>Your Sales Team</strong></p>
                    </div>

                    <div style="text-align: center; padding: 20px; color: #888; font-size: 12px;">
                        <p>This is an automated email. Please do not reply directly to this message.</p>
                    </div>
                </div>
            </body>
        </html>
        """

        email_sent = send_email(user_email, subject, body)

        if email_sent:
            _EMAIL_NOTIFY_LAST_SENT[rate_key] = now
            print(f"[EMAIL] Quotation pending email sent to {user_email} for {docno}")
            return jsonify({
                'success': True,
                'message': f'Quotation pending email sent to {user_email}'
            })
        return jsonify({
            'success': False,
            'error': 'Failed to send email. Please check email configuration.'
        }), 500

    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send quotation email: {e}")
        return jsonify({'success': False, 'error': 'Failed to send quotation email'}), 500


@quotation_bp.route('/api/customer/sql_api_currency', methods=['GET'])
def api_customer_sql_api_currency():
    """Currency + code from SQL API GET /customer (Flask session; display only)."""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    customer_code = (session.get('customer_code') or '').strip()
    if not customer_code:
        user_email = (session.get('user_email') or '').strip()
        if user_email:
            try:
                from utils.db_utils import db_connection
                from utils.sql_query_helpers import find_customer_code_by_email

                with db_connection() as con:
                    cur = con.cursor()
                    try:
                        customer_code = find_customer_code_by_email(cur, user_email) or ''
                    finally:
                        cur.close()
            except Exception:
                customer_code = ''

    if not customer_code:
        return jsonify({'success': False, 'error': 'Customer code not found'}), 400

    from utils.sql_api_customer import sql_api_currency_and_code

    fields = sql_api_currency_and_code(customer_code)
    return jsonify({
        'success': True,
        'sqlApiCustomerCode': fields.get('code') or customer_code,
        'sqlApiCurrencyCode': fields.get('currencycode', ''),
        'source': 'sql_api_customer_get',
    })
