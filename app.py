import streamlit as st
from gst_checker import extract_text_from_pdf, get_invoice_feedback
import os
from gst_checker import extract_text_from_excel
import requests
from gst_checker import generate_pdf_report
import pymongo
import hashlib
import random
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from email_validator import validate_email, EmailNotValidError
from datetime import date
import json
import re
import ast
from dotenv import load_dotenv
import os
st.set_page_config(page_title="GST Invoice Checker", page_icon="🧾", layout="centered")
load_dotenv()  # Loads variables from .env into environment

openai_api_key = os.getenv("OPENAI_API_KEY")
# Enhanced custom CSS for a modern look
st.markdown("""
    <style>
    .main { background-color: #f4f6fb; }
    .stButton>button { background-color: #4F8EF7; color: white; border-radius: 8px; font-size: 18px; padding: 0.5em 2em; }
    .stButton>button:hover { background-color: #1746A2; }
    .pricing-table { width: 100%; border-collapse: collapse; margin-top: 1em; }
    .pricing-table th, .pricing-table td { border: 1px solid #e0e0e0; padding: 1em; text-align: center; font-size: 18px; color: #222; }
    .pricing-table th { background: #4F8EF7; color: white; }
    .pricing-table td { background: #fff; color: #222; }
    .plan-free { color: #4F8EF7; font-weight: bold; }
    .plan-basic { color: #F7B32B; font-weight: bold; }
    .plan-pro { color: #E94F37; font-weight: bold; }
    footer { visibility: hidden; }
    </style>
""", unsafe_allow_html=True)

st.title("🧾 GST Invoice Checker (AI-Powered)")
st.caption("Easily detect common errors in your invoices using AI. Built with 💡 by students in India.")

# Add a button to show the payment chart
show_pricing = st.button("💳 View Plans & Pricing")
if show_pricing or st.session_state.get('show_pricing', False):
    st.session_state['show_pricing'] = True
    with st.expander("Pricing Plans", expanded=True):
        col1, col2, col3, col4 = st.columns([2,2,4,2])
        with col1:
            st.markdown('<span class="plan-free" style="font-size:1.2em;">Free</span>', unsafe_allow_html=True)
            st.markdown('<b>₹0</b>', unsafe_allow_html=True)
            st.markdown('Upload 50 files/day, view feedback, no download', unsafe_allow_html=True)
            # Only allow Get Started if not logged in to just show login, not file upload
            if st.button('Get Started', key='free_get_started_btn'):
                st.session_state['show_pricing'] = False
                if st.session_state.get('user'):
                    st.session_state['show_file_upload'] = True
                else:
                    st.session_state['show_login'] = True
        with col2:
            st.markdown('<span class="plan-basic" style="font-size:1.2em;">Basic</span>', unsafe_allow_html=True)
            st.markdown('<b>₹149</b>', unsafe_allow_html=True)
            st.markdown('200 files/day, view & download feedback', unsafe_allow_html=True)
            st.markdown("<a href='https://rzp.io/rzp/QV3yYz49' target='_blank'><button type='button' style='background:#F7B32B;color:white;border:none;padding:0.5em 1.5em;border-radius:6px;font-size:16px;cursor:pointer;'>Buy</button></a>", unsafe_allow_html=True)
        with col3:
            st.markdown('<span class="plan-pro" style="font-size:1.2em;">Pro</span>', unsafe_allow_html=True)
            st.markdown('<b>₹299</b>', unsafe_allow_html=True)
            st.markdown('Unlimited usage, PDF + Excel export, early access to new tools', unsafe_allow_html=True)
            st.markdown("<a href='https://rzp.io/rzp/uKlFgK1O' target='_blank'><button type='button' style='background:#E94F37;color:white;border:none;padding:0.5em 1.5em;border-radius:6px;font-size:16px;cursor:pointer;'>Buy</button></a>", unsafe_allow_html=True)
        st.info("Contact us to upgrade your plan!")

# MongoDB setup
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
# Debug: Print the URI being used (remove this after fixing)
print(f"Using MongoDB URI: {MONGO_URI}")

try:
    client = pymongo.MongoClient(MONGO_URI)
    # Test the connection
    client.admin.command('ping')
    print("MongoDB connection successful!")
    db = client['gst_invoice_checker']
    users_col = db['users']
except Exception as e:
    print(f"MongoDB connection failed: {e}")
    st.error(f"Database connection failed: {e}")
    # Create a dummy client to prevent crashes
    client = None
    db = None
    users_col = None

# Email sender setup (configure for your SMTP server)
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_EMAIL = 'beingbyte2025@gmail.com'  # <-- Replace with your email
SMTP_PASSWORD = 'rmqb rivh werz qlhl'  # <-- Replace with your app password

# Helper functions

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def send_otp_email(email, otp):
    msg = MIMEText(f"Your OTP for GST Invoice Checker is: {otp}")
    msg['Subject'] = 'GST Invoice Checker OTP Verification'
    msg['From'] = SMTP_EMAIL
    msg['To'] = email
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, [email], msg.as_string())
        return True
    except Exception as e:
        st.error(f"Failed to send OTP: {e}")
        return False

def generate_otp():
    return str(random.randint(100000, 999999))

# Helper for daily usage

def can_upload(user, plan):
    today = date.today().isoformat()
    usage = user.get('usage', {})
    count = usage.get(today, 0)
    if plan == 'Free':
        return count < 50  # Increased from 20 to 50
    elif plan == 'Basic':
        return count < 200  # Increased from 65 to 200
    elif plan == 'Pro':
        return True
    return False

def increment_usage(email):
    if not users_col:
        return
    try:
        today = date.today().isoformat()
        user = users_col.find_one({'email': email})
        usage = user.get('usage', {})
        usage[today] = usage.get(today, 0) + 1
        users_col.update_one({'email': email}, {'$set': {'usage': usage}})
    except Exception as e:
        print(f"Error incrementing usage: {e}")

def can_download(user, plan):
    today = date.today().isoformat()
    downloads = user.get('downloads', {})
    count = downloads.get(today, 0)
    if plan == 'Free':
        return count < 2
    elif plan == 'Basic':
        return True
    elif plan == 'Pro':
        return True
    return False

def increment_download(email):
    if not users_col:
        return
    try:
        today = date.today().isoformat()
        user = users_col.find_one({'email': email})
        downloads = user.get('downloads', {})
        downloads[today] = downloads.get(today, 0) + 1
        users_col.update_one({'email': email}, {'$set': {'downloads': downloads}})
    except Exception as e:
        print(f"Error incrementing download: {e}")

# Helper function to send renewal email

def send_renewal_email(email, plan):
    msg = MIMEText(f"Your {plan} plan on GST Invoice Checker has expired. Please renew to continue enjoying premium features!")
    msg['Subject'] = f'GST Invoice Checker: {plan} Plan Expired'
    msg['From'] = SMTP_EMAIL
    msg['To'] = email
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, [email], msg.as_string())
        return True
    except Exception as e:
        st.error(f"Failed to send renewal email: {e}")
        return False

def extract_json_from_string(s):
    match = re.search(r'({.*})', s, re.DOTALL)
    if match:
        return match.group(1)
    return None

def safe_json_parse(s):
    try:
        return json.loads(s)
    except Exception:
        # Try to fix common issues: single quotes, trailing commas, newlines
        s_fixed = s.replace("'", '"').replace('\n', '').replace('\r', '')
        try:
            return json.loads(s_fixed)
        except Exception:
            # Try Python dict eval as last resort
            try:
                return ast.literal_eval(s)
            except Exception:
                return None

# On login or app use, check plan expiry
user_email = st.session_state.get('user')
if user_email:
    user = users_col.find_one({'email': user_email})
    plan = user.get('plan', 'Free')
    plan_expiry = user.get('plan_expiry')
    if plan in ['Basic', 'Pro'] and plan_expiry:
        try:
            expiry_dt = datetime.fromisoformat(str(plan_expiry))
            if datetime.utcnow() > expiry_dt:
                # Downgrade to Free and send renewal email
                users_col.update_one({'email': user_email}, {'$set': {'plan': 'Free'}, '$unset': {'plan_expiry': ''}})
                st.session_state['plan_expired'] = True
                send_renewal_email(user_email, plan)
                plan = 'Free'
        except Exception:
            pass
    else:
        st.session_state['plan_expired'] = False

# Show message if plan expired
if st.session_state.get('plan_expired', False):
    st.warning('Your paid plan has expired. Please renew to continue enjoying premium features!')

# When upgrading plan (admin/manual/after payment), set plan_expiry to 30 days from now:
# Example usage:
# users_col.update_one({'email': user_email}, {'$set': {'plan': 'Basic', 'plan_expiry': (datetime.datetime.utcnow() + datetime.timedelta(days=30)).isoformat()}})

# --- Top-right Login/User Button and Modal Logic (Single Page) ---
if 'show_login' not in st.session_state:
    st.session_state['show_login'] = False
if 'show_signup' not in st.session_state:
    st.session_state['show_signup'] = False
if 'show_otp' not in st.session_state:
    st.session_state['show_otp'] = False
if 'signup_email' not in st.session_state:
    st.session_state['signup_email'] = ''
if 'signup_name' not in st.session_state:
    st.session_state['signup_name'] = ''
if 'show_file_upload' not in st.session_state:
    st.session_state['show_file_upload'] = False
if 'show_pricing' not in st.session_state:
    st.session_state['show_pricing'] = False

user_email = st.session_state.get('user')
user_name = None
if user_email and users_col is not None:
    try:
        user = users_col.find_one({'email': user_email})
        user_name = user.get('name', user_email.split('@')[0]) if user else user_email.split('@')[0]
    except Exception as e:
        print(f"Error finding user: {e}")
        user_name = user_email.split('@')[0]
elif user_email:
    user_name = user_email.split('@')[0]

login_btn_css = """
<style>
#custom-login-btn {
    position: absolute;
    top: 1.2rem;
    right: 2.5rem;
    z-index: 9999;
}
</style>
<div id='custom-login-btn'></div>
"""
st.markdown(login_btn_css, unsafe_allow_html=True)

with st.container():
    st.markdown('<div id="custom-login-btn">', unsafe_allow_html=True)
    if user_email:
        if st.button(f'👤 {user_name}', key='user_top_btn'):
            st.session_state['show_user_menu'] = not st.session_state.get('show_user_menu', False)
    else:
        if st.button('🔐 Login', key='login_top_btn'):
            st.session_state['show_login'] = True
            st.session_state['show_signup'] = False
            st.session_state['show_otp'] = False
    st.markdown('</div>', unsafe_allow_html=True)

# Login Modal
if st.session_state['show_login']:
    st.markdown('---')
    st.subheader('Login to your account')
    login_email = st.text_input('Email', key='login_email_modal')
    login_password = st.text_input('Password', type='password', key='login_password_modal')
    if st.button('Login', key='login_btn_modal'):
        user = users_col.find_one({'email': login_email})
        if user and user['password'] == hash_password(login_password):
            if user.get('is_verified', False):
                st.session_state['user'] = login_email
                st.success(f'Logged in as {login_email}')
                st.session_state['show_login'] = False
            else:
                st.warning('Please verify your email before logging in.')
        else:
            st.error('Invalid credentials.')
    if st.button('Sign Up', key='goto_signup_btn'):
        st.session_state['show_signup'] = True
        st.session_state['show_login'] = False

# Sign Up Modal
if st.session_state['show_signup']:
    st.markdown('---')
    st.subheader('Create a new account')
    signup_name_input = st.text_input('Name', key='signup_name_input')
    signup_email_input = st.text_input('Email', key='signup_email_input')
    signup_password = st.text_input('Password', type='password', key='signup_password')
    signup_confirm = st.text_input('Confirm Password', type='password', key='signup_confirm')
    signup_error = ''
    if st.button('Sign Up', key='signup_btn'):
        if not signup_name_input.strip():
            signup_error = 'Name is required.'
        elif not signup_email_input.strip():
            signup_error = 'Email is required.'
        elif not signup_password or not signup_confirm:
            signup_error = 'Password and confirmation are required.'
        elif signup_password != signup_confirm:
            signup_error = 'Passwords do not match.'
        else:
            try:
                validate_email(signup_email_input)
                if users_col.find_one({'email': signup_email_input}):
                    signup_error = 'Email already registered.'
                else:
                    otp = generate_otp()
                    otp_expiry = datetime.utcnow() + timedelta(minutes=10)
                    users_col.insert_one({
                        'name': signup_name_input,
                        'email': signup_email_input,
                        'password': hash_password(signup_password),
                        'plan': 'Free',
                        'is_verified': False,
                        'otp': otp,
                        'otp_expiry': otp_expiry
                    })
                    if send_otp_email(signup_email_input, otp):
                        st.session_state['show_otp'] = True
                        st.session_state['signup_email'] = signup_email_input
                        st.session_state['signup_name'] = signup_name_input
                        st.session_state['show_signup'] = False
                        st.success('OTP sent to your email. Please verify.')
            except EmailNotValidError as e:
                signup_error = str(e)
        if signup_error:
            st.error(signup_error)
    if st.button('Go to Login', key='goto_login_btn'):
        st.session_state['show_login'] = True
        st.session_state['show_signup'] = False

# OTP Verification Modal
if st.session_state['show_otp']:
    st.markdown('---')
    st.subheader('Verify your email')
    otp_input = st.text_input('Enter OTP (sent to your email)', key='otp_input')
    if st.button('Verify OTP', key='verify_otp_btn'):
        user = users_col.find_one({'email': st.session_state['signup_email']})
        if user and user['otp'] == otp_input and datetime.utcnow() < user['otp_expiry']:
            users_col.update_one({'email': st.session_state['signup_email']}, {'$set': {'is_verified': True}, '$unset': {'otp': '', 'otp_expiry': ''}})
            st.success('Email verified! You can now log in.')
            st.session_state['show_otp'] = False
            st.session_state['show_login'] = True
        else:
            st.error('Invalid or expired OTP.')

# --- User menu dropdown for logout
if st.session_state.get('show_user_menu', False):
    if st.button('Logout', key='logout_btn', help='Log out of your account'):
        st.session_state.clear()
        # Explicitly clear all UI flags
        st.session_state['show_login'] = False
        st.session_state['show_signup'] = False
        st.session_state['show_otp'] = False
        st.session_state['show_user_menu'] = False
        st.session_state['show_file_upload'] = False
        st.session_state['show_pricing'] = False
        st.rerun()

# Add a big arrow and message to guide users to the sidebar for login
if not st.session_state.get('user'):
    st.markdown('''
        <div style="display: flex; align-items: center; margin-top: 2em; margin-bottom: 2em;">
            <span style="font-size: 3em; color: #4F8EF7; margin-right: 0.5em;">⬅️</span>
            <span style="font-size: 1.5em; color: #4F8EF7; font-weight: bold;">Login here (use the sidebar on the left)</span>
        </div>
    ''', unsafe_allow_html=True)

# Main app logic gated by login
user_email = st.session_state.get('user')
if user_email and users_col is not None:
    try:
        user = users_col.find_one({'email': user_email})
        plan = user.get('plan', 'Free') if user else 'Free'
    except Exception as e:
        print(f"Error finding user for main app: {e}")
        plan = 'Free'
elif user_email:
    plan = 'Free'
else:
    plan = 'Free'

if user_email:
    st.sidebar.info(f'Plan: {plan}')
    st.sidebar.write('Upgrade your plan for more features!')

    # Plan features
    plan_features = {
        'Free': 'Upload 50 files/day, view feedback, no download',
        'Basic': '200 files/day, view & download feedback',
        'Pro': 'Unlimited usage, PDF + Excel export, early access to new tools'
    }
    st.sidebar.write(f'**Features:** {plan_features[plan]}')

    # Usage gating
    if not can_upload(user, plan):
        st.error(f"You have reached your daily upload limit for the {plan} plan.")
    else:
        # Show file upload and analysis UI if user is logged in or has selected Free plan
        if st.session_state.get('user') or st.session_state.get('show_file_upload'):
            uploaded_file = st.file_uploader("📂 Upload a GST Invoice (PDF or Excel)", type=["pdf", "xlsx"])
            po_file = st.file_uploader("📂 Upload a Purchase Order (PO) (PDF or Excel)", type=["pdf", "xlsx"], key="po_file")
            grn_file = st.file_uploader("📂 Upload a Goods Receipt Note (GRN) (PDF or Excel)", type=["pdf", "xlsx"], key="grn_file")

            if uploaded_file is not None:
                st.info(f"✅ File uploaded: `{uploaded_file.name}`")
            if po_file is not None:
                st.info(f"✅ PO file uploaded: `{po_file.name}`")
            if grn_file is not None:
                st.info(f"✅ GRN file uploaded: `{grn_file.name}`")

            # Only show validation button if all three files are uploaded
            if uploaded_file and po_file and grn_file:
                if st.button("🧠 Run Document Validation"):
                    with st.spinner("Extracting and validating all documents..."):
                        # Extract text from all files
                        if uploaded_file.name.endswith(".pdf"):
                            invoice_text = extract_text_from_pdf(uploaded_file)
                        elif uploaded_file.name.endswith(".xlsx"):
                            invoice_text = extract_text_from_excel(uploaded_file)
                        else:
                            st.error("Unsupported file format for Invoice.")
                            invoice_text = ""

                        if po_file.name.endswith(".pdf"):
                            po_text = extract_text_from_pdf(po_file)
                        elif po_file.name.endswith(".xlsx"):
                            po_text = extract_text_from_excel(po_file)
                        else:
                            st.error("Unsupported file format for PO.")
                            po_text = ""

                        if grn_file.name.endswith(".pdf"):
                            grn_text = extract_text_from_pdf(grn_file)
                        elif grn_file.name.endswith(".xlsx"):
                            grn_text = extract_text_from_excel(grn_file)
                        else:
                            st.error("Unsupported file format for GRN.")
                            grn_text = ""

                        # Debug: Print extracted text to logs
                        print("INVOICE TEXT:", invoice_text)
                        print("PO TEXT:", po_text)
                        print("GRN TEXT:", grn_text)

                        # Validate all three
                        from gst_checker import validate_3way
                        result = validate_3way(invoice_text, po_text, grn_text)
                        verdict = result.get("verdict", "Not ready to process")
                        error = result.get("error")
                        st.markdown(f"## 🏁 Final Verdict: **{verdict}**")
                        if error:
                            st.error(f"❌ Error: {error}")
                        else:
                            st.success("All documents validated successfully!")

else:
    st.warning("Please log in to use the GST Invoice Checker.")
    
