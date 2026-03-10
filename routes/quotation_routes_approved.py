"""Quotation approved/ready email routes."""
from datetime import datetime
from flask import Blueprint, request, jsonify
from utils import send_email

# Create Blueprint for approved quotation routes
quotation_approved_bp = Blueprint('quotation_approved', __name__)


@quotation_approved_bp.route('/api/send_quotation_ready_email', methods=['POST'])
def send_quotation_ready_email():
    """Send quotation ready for review email to customer"""
    data = request.get_json() or {}
    customer_email = data.get('customerEmail')
    docno = data.get('docno', 'N/A')
    dockey = data.get('dockey', 'N/A')
    total_amount = data.get('totalAmount', 0)
    items = data.get('items', [])
    company_name = data.get('companyName', 'Valued Customer')
    
    if not customer_email:
        return jsonify({'success': False, 'error': 'Customer email is required'}), 400
    
    try:
        # Create email body with quotation details
        items_html = ''
        for idx, item in enumerate(items, 1):
            product = item.get('product', '') or item.get('DESCRIPTION', '')
            qty = item.get('qty', 0) or item.get('QTY', 0)
            price = item.get('price', 0) or item.get('UNITPRICE', 0)
            subtotal = qty * price
            items_html += f'''
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #e0e0e0;">{idx}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e0e0e0;">{product}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e0e0e0; text-align: center;">{qty}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e0e0e0; text-align: right;">RM {price:.2f}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e0e0e0; text-align: right;">RM {subtotal:.2f}</td>
            </tr>
            '''
        
        subject = f"Quotation {docno} - Ready for Review"
        body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9; border-radius: 8px;">
                    <div style="background-color: #4b9e6e; color: #fff; padding: 20px; border-radius: 8px 8px 0 0; text-align: center;">
                        <h1 style="margin: 0;">Quotation Ready for Review</h1>
                    </div>
                    
                    <div style="background-color: #fff; padding: 30px; border-radius: 0 0 8px 8px;">
                        <p style="font-size: 16px;">Dear {company_name},</p>
                        
                        <p>Your quotation has been <strong>approved and is now ready for your review</strong>.</p>
                        
                        <div style="background-color: #e8f5e9; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #4b9e6e;">
                            <p style="margin: 5px 0;"><strong>Quotation Number:</strong> {docno}</p>
                            <p style="margin: 5px 0;"><strong>Status:</strong> <span style="color: #4b9e6e; font-weight: bold;">Active</span></p>
                            <p style="margin: 5px 0;"><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                        </div>
                        
                        <h3 style="color: #1a1f2e; border-bottom: 2px solid #1a1f2e; padding-bottom: 10px;">Quotation Details</h3>
                        
                        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                            <thead>
                                <tr style="background-color: #1a1f2e; color: #fff;">
                                    <th style="padding: 10px; text-align: left;">#</th>
                                    <th style="padding: 10px; text-align: left;">Product</th>
                                    <th style="padding: 10px; text-align: center;">Qty</th>
                                    <th style="padding: 10px; text-align: right;">Unit Price</th>
                                    <th style="padding: 10px; text-align: right;">Subtotal</th>
                                </tr>
                            </thead>
                            <tbody>
                                {items_html}
                            </tbody>
                            <tfoot>
                                <tr style="background-color: #f5f5f5; font-weight: bold;">
                                    <td colspan="4" style="padding: 15px; text-align: right;">Total Amount:</td>
                                    <td style="padding: 15px; text-align: right;">RM {total_amount:.2f}</td>
                                </tr>
                            </tfoot>
                        </table>
                        
                        <div style="background-color: #e8f5e9; padding: 15px; border-left: 4px solid #4b9e6e; margin: 20px 0;">
                            <p style="margin: 0;"><strong>Next Steps:</strong></p>
                            <p style="margin: 10px 0 0 0;">You can now review this quotation and proceed with your order. Please log in to your account to view the full details and take action.</p>
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
        
        # Send the email
        email_sent = send_email(customer_email, subject, body)
        
        if email_sent:
            print(f"[EMAIL] Quotation ready email sent to {customer_email} for {docno}")
            return jsonify({
                'success': True,
                'message': f'Quotation ready email sent to {customer_email}'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send email. Please check email configuration.'
            }), 500
            
    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send quotation ready email: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
