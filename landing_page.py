import streamlit as st
from gst_checker import extract_text_from_pdf, extract_text_from_excel, get_invoice_feedback

st.set_page_config(page_title="GSTAI — Smart GST Invoice Checker", page_icon="🧾", layout="centered")

# Custom CSS for better layout
st.markdown("""
    <style>
    .main { background-color: #f9f9f9; padding: 2rem; }
    h1, h2, h3 { color: #1a73e8; }
    .block { background: white; padding: 1.5rem; border-radius: 12px; box-shadow: 0 0 8px rgba(0,0,0,0.05); margin-bottom: 2rem; }
    footer { visibility: hidden; }
    </style>
""", unsafe_allow_html=True)

# Hero Section
st.markdown("<div class='block'>", unsafe_allow_html=True)
st.markdown("## 🧾 GSTAI — Instant Invoice Checker")
st.write("An AI-powered tool that helps businesses, accountants, and freelancers quickly validate GST invoices for errors and compliance.")
st.success("Try uploading your invoice below (PDF or Excel). No login required.")
st.markdown("</div>", unsafe_allow_html=True)

# Upload + Feedback Block
st.markdown("<div class='block'>", unsafe_allow_html=True)
uploaded_file = st.file_uploader("📂 Upload a GST Invoice (PDF or Excel)", type=["pdf", "xlsx"])

if uploaded_file:
    if uploaded_file.name.endswith(".pdf"):
        text = extract_text_from_pdf(uploaded_file)
    elif uploaded_file.name.endswith(".xlsx"):
        text = extract_text_from_excel(uploaded_file)
    else:
        st.error("Unsupported format.")
        text = ""

    if text:
        st.subheader("📝 Invoice Extracted Text")
        st.code(text[:1500], language="text")

        if st.button("💬 Get Feedback (Mock AI)"):
            feedback = get_invoice_feedback(text, use_mock=True)
            st.success("✅ Feedback generated below")
            st.text_area("🧠 AI Feedback", feedback, height=300)
else:
    st.info("Upload a file to see the feedback system in action.")

st.markdown("</div>", unsafe_allow_html=True)

# Features Section
st.markdown("<div class='block'>", unsafe_allow_html=True)
st.markdown("### 💡 Features")
st.markdown("""
- 🔍 Auto-analysis of invoices using AI  
- 📄 Supports PDF & Excel formats  
- 🧠 Smart error detection (mock or real GPT)  
- 📥 Download feedback as PDF  
- 🆓 Use without any signup
""")
st.markdown("</div>", unsafe_allow_html=True)

# Footer
st.markdown("<div class='block'>", unsafe_allow_html=True)
st.markdown("### 👨‍💻 About Us")
st.write("Built by a student team in India to simplify GST compliance for SMEs and finance professionals.")
st.markdown("📬 Contact: [support@gstai.in](mailto:support@gstai.in)")
st.caption("Made with ❤️ in India | #BuildInPublic")
st.markdown("</div>", unsafe_allow_html=True)
