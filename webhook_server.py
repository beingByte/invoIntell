from flask import Flask, request, jsonify
import pymongo
import datetime

app = Flask(__name__)

# MongoDB setup
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client['gst_invoice_checker']
users_col = db['users']

# Replace with your Razorpay webhook secret (set in Razorpay dashboard)
RAZORPAY_WEBHOOK_SECRET = "your_webhook_secret"

@app.route('/razorpay-webhook', methods=['POST'])
def razorpay_webhook():
    data = request.json

    # 1. Verify webhook signature (for security, see Razorpay docs)
    # 2. Check payment status
    # 3. Identify user (e.g., by email or custom field in payment link)
    # 4. Update user plan and expiry

    # Example: Assume you pass user's email as 'notes' in Razorpay payment link
    if data.get('event') == 'payment.captured':
        payment = data['payload']['payment']['entity']
        email = payment['notes'].get('email')  # You must set this in your payment link!
        plan = payment['notes'].get('plan')    # 'Basic' or 'Pro'
        if email and plan in ['Basic', 'Pro']:
            users_col.update_one(
                {'email': email},
                {'$set': {
                    'plan': plan,
                    'plan_expiry': (datetime.datetime.utcnow() + datetime.timedelta(days=30)).isoformat()
                }}
            )
            return jsonify({'status': 'success'}), 200

    return jsonify({'status': 'ignored'}), 200

if __name__ == '__main__':
    app.run(port=5001) 