import hashlib
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
import pandas as pd
import random
import re
import os
import tempfile
from difflib import get_close_matches
import streamlit as st
import kagglehub
import database
import calendar_utils
import symptom_analyzer
import voice_utils
from streamlit_mic_recorder import mic_recorder
from gtts import gTTS
import base64

DEFAULT_DOCTORS = {
    "Primary Care Doctor": ["Dr. Rajesh Sharma", "Dr. Anita Desai", "Dr. Amit Patel"],
    "Cardiologist": ["Dr. Suresh Raina", "Dr. Meena Gupta", "Dr. Vikram Seth"],
    "Dermatologist": ["Dr. Priya Nair", "Dr. Kunal Kapoor", "Dr. Pooja Joshi"],
    "Neurologist": ["Dr. Arun Kumar", "Dr. Sunita Rao", "Dr. Deepak Verma"],
    "Orthopedic Surgeon": ["Dr. Alok Mishra", "Dr. Ritu Choudhary", "Dr. Sanjay Dutt"],
    "Pediatrician": ["Dr. Neha Bansal", "Dr. Rahul Malhotra", "Dr. Simran Kaur"],
    "Psychiatrist": ["Dr. Manisha Roy", "Dr. Rohit Agarwal", "Dr. Tanvi Shah"],
    "Ear, Nose & Throat Doctor": ["Dr. Vivek Reddy", "Dr. Swati Sen", "Dr. Gautam Das"],
    "Ophthalmologist": ["Dr. Arvind Swamy", "Dr. Pallavi Kulkarni", "Dr. Tarun Jain"],
    "Dentist": ["Dr. Ananya Pandey", "Dr. Harshvardhan Goel", "Dr. Divya Iyer"],
    "Gastroenterologist": ["Dr. Pradeep Bhat", "Dr. Smita Tiwari", "Dr. Mohit Saxena"],
    "Pulmonologist": ["Dr. Sandeep Mukherjee", "Dr. Shweta Singh", "Dr. Farhan Akhtar"],
    "Urologist": ["Dr. Harish Chandra", "Dr. Radhika Menon", "Dr. Nikhil Pillai"]
}

@st.cache_resource
def load_doctor_data():
    try:
        path = kagglehub.dataset_download("niksaurabh/doctors-speciality")
        csv_files = [file for file in os.listdir(path) if file.endswith('.csv')]
        if csv_files:
            file_path = os.path.join(path, csv_files[0])
            df = pd.read_csv(file_path)
            data = df.groupby('speciality')['Doctor\'s Name'].apply(list).to_dict()
            if data:
                return data
    except Exception as e:
        print(f"Notice: Using default doctor directory (KaggleHub note: {e})")
    return DEFAULT_DOCTORS

doctors_by_specialty = load_doctor_data()

def send_email(to_email, subject, body):
    sender_email = "adityaraj6112025@gmail.com"
    password = "kjowmfcicgzkqnti"
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = to_email
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, to_email, msg.as_string())
        st.success("Email sent successfully!")
    except Exception as e:
        st.error(f"Error sending email: {e}")

def validate_mobile(mobile):
    return re.match(r'^\d{10}$', mobile) is not None

def parse_date(date_str):
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError: continue
    return None

def parse_time(time_str):
    if not time_str: return None
    t = time_str.lower().replace(".", "").replace(" ","").strip()
    formats = ["%I:%M%p", "%I%p", "%H:%M", "%I.%M%p"]
    for fmt in formats:
        try:
            return datetime.strptime(t, fmt).strftime("%I:%M %p")
        except ValueError: continue
    if "noon" in t: return "12:00 PM"
    if "midnight" in t: return "12:00 AM"
    return None

def is_past_date(date_str):
    return date_str < datetime.today().strftime("%Y-%m-%d")

def is_past_time(date_str, time_str):
    if date_str == datetime.today().strftime("%Y-%m-%d"):
        return time_str < datetime.now().strftime("%I:%M %p")
    return False

def is_time_slot_available(date_str, time_str, doctor):
    return database.check_availability(date_str, time_str, doctor)

def speak_text(text):
    if not text: return
    try:
        # Normalize text for speech (e.g. remove numbering for cleaner speech)
        clean_text = re.sub(r'^\d+\.\s*', '', text, flags=re.MULTILINE)
        tts = gTTS(text=clean_text, lang='en', tld='co.in')
        fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        try:
            tts.save(tmp_path)
            with open(tmp_path, "rb") as f:
                data = f.read()
                b64 = base64.b64encode(data).decode()
                # Use style="display:none" to hide the audio player
                md = f'<audio autoplay="true" style="display:none;"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>'
                st.markdown(md, unsafe_allow_html=True)
        finally:
            if os.path.exists(tmp_path): os.remove(tmp_path)
    except Exception as e: print(f"TTS Error: {e}")

def normalize_input(text):
    if not text: return ""
    text = text.lower().strip()
    word_to_digit = {"one": "1", "book": "1", "two": "2", "reschedule": "2", "three": "3", "cancel": "3", "four": "4", "medical": "4", "five": "5"}
    for word, digit in word_to_digit.items():
        if word in text: return digit
    digits = re.findall(r'\d+', text)
    return digits[0] if digits else text

def get_next_missing_field():
    required = ["name", "email", "mobile", "age", "gender", "symptoms", "selected_doctor", "appointment_date", "appointment_time"]
    details = st.session_state["appointment_details"]
    for field in required:
        if not details.get(field): return field
    return "confirm_appointment"

def is_complex_input(text, current_step=None):
    if not text: return False
    if current_step in ["symptoms", "appointment_time", "appointment_date"]:
        if not re.match(r'^\d{1,2}$', text.strip()): return True
    words = text.strip().split()
    if len(words) > 4: return True
    keywords = ["and", "have", "with", "my", "is", "am", "at", "on"]
    if any(k in text.lower() for k in keywords) and len(words) > 2: return True
    return False

def ask_step_question(step):
    questions = {
        "name": "What's your full name?",
        "email": "What's your email address?",
        "mobile": "What's your mobile number?",
        "age": "What's your age?",
        "gender": "What's your gender? (Male, Female, or Transgender)",
        "symptoms": "What symptoms are you having?",
        "appointment_date": "When would you like to visit?",
        "appointment_time": "What time?",
        "confirm_appointment": "Ready to book?",
        "reschedule_email": "Please enter your registered email address to locate your appointment:",
        "cancel_email": "Please enter your registered email address to locate your appointment:"
    }
    msg = questions.get(step)
    if msg and (not st.session_state["messages"] or st.session_state["messages"][-1]["content"] != msg):
        st.session_state["messages"].append({"role": "assistant", "content": msg})
        st.session_state["to_speak"] = msg

def inject_custom_css():
    css = """<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@400;600;700&display=swap" rel="stylesheet"><style>@keyframes meshGradient { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(99, 102, 241, 0.4); transform: scale(1); } 70% { box-shadow: 0 0 0 20px rgba(99, 102, 241, 0); transform: scale(1.05); } 100% { box-shadow: 0 0 0 0 rgba(99, 102, 241, 0); transform: scale(1); } }.stApp { background-color: #030712; background-image: radial-gradient(circle at 20% 20%, rgba(79, 70, 229, 0.15) 0% , transparent 50%), radial-gradient(circle at 80% 80%, rgba(99, 102, 241, 0.15) 0%, transparent 50%), radial-gradient(circle at 50% 50%, rgba(31, 41, 55, 0.2) 0%, transparent 70%); background-size: 200% 200%; animation: meshGradient 20s ease infinite; background-attachment: fixed; font-family: 'Inter', sans-serif; }.title { font-family: 'Outfit', sans-serif; font-size: clamp(28px, 5vw, 46px); font-weight: 700; background: linear-gradient(135deg, #ffffff 0%, #818cf8 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-align: center; padding: 20px 10px 40px; filter: drop-shadow(0 4px 12px rgba(0,0,0,0.4)); }.stChatMessage { border-radius: 24px !important; padding: 1.2rem !important; border: 1px solid rgba(255, 255, 255, 0.1) !important; background: rgba(15, 23, 42, 0.8) !important; backdrop-filter: blur(30px); margin-bottom: 1.2rem !important; } /* PRECISION HIDE LABELS */ .stChatMessage [data-testid="stChatMessageAvatar"] + div > div:first-child:not([data-testid="stMarkdownContainer"]), [data-testid="stChatMessage"] header, div[class*="ChatMessageName"] { display: none !important; font-size: 0 !important; visibility: hidden !important; height: 0 !important; } .stChatMessage p, .stChatMessage li, .stChatMessage span, .stChatMessage div { color: #ffffff !important; font-family: 'Inter', sans-serif !important; font-size: 1rem !important; line-height: 1.6 !important; }.dashboard-item { background: rgba(31, 41, 55, 0.6); padding: 20px; border-radius: 20px; margin-bottom: 15px; border-left: 5px solid #6366f1; transition: 0.3s; }.dashboard-item:hover { transform: translateY(-2px); background: rgba(31, 41, 55, 0.8); }.assistant-header { color: #a5b4fc !important; font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 1.2rem; letter-spacing: 2px; margin-bottom: 20px; text-transform: uppercase; }.stMicRecorder button { background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%) !important; color: white !important; padding: 12px 30px !important; border-radius: 100px !important; font-family: 'Outfit', sans-serif !important; font-weight: 700 !important; font-size: 1rem !important; text-transform: uppercase !important; letter-spacing: 2px !important; transition: 0.4s all cubic-bezier(0.175, 0.885, 0.32, 1.275) !important; cursor: pointer !important; width: 100% !important; } .stMicRecorder button [data-recording="true"] { background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%) !important; animation: pulse 1.5s infinite !important; }@media (max-width: 900px) { [data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; } }@media (max-width: 768px) { .stChatMessage { padding: 1rem !important; border-radius: 16px !important; } .dashboard-item { padding: 15px !important; } }div[data-testid="stChatInput"] { background-color: rgba(255, 255, 255, 0.95) !important; border: 2px solid #6366f1 !important; border-radius: 20px !important; }#MainMenu, header, footer {visibility: hidden;}</style>"""
    st.markdown(css, unsafe_allow_html=True)

def handle_chat():
    if "step" not in st.session_state: st.session_state["step"] = None
    if "messages" not in st.session_state: st.session_state["messages"] = []
    if "appointment_details" not in st.session_state: st.session_state["appointment_details"] = {}
    if "audio_key_index" not in st.session_state: st.session_state["audio_key_index"] = 0

    # 0. DATABASE STATUS & RESILIENCE
    is_connected, db_status = database.test_connection()
    if not is_connected:
        with st.expander("ℹ️ Database Notice: Local Fallback Active", expanded=False):
            st.warning(f"**Notice:** {db_status}")
            st.markdown("""
            **Why is this happening?**
            - Free-tier Supabase projects pause after 7 days of inactivity.
            - **To resume cloud synchronization:**
              1. Log into your [Supabase Dashboard](https://supabase.com/dashboard).
              2. Select your project and click **'Restore project'** (takes ~1-2 mins).
              3. Verify `SUPABASE_URL` and `SUPABASE_KEY` in your Streamlit Cloud Secrets.
            
            *The assistant is fully functional in Local Fallback mode right now. You can book, check symptoms, and chat normally!*
            """)

    # Create Main Columns (Left for Chat, Right for Dashboard)
    col_chat, col_dash = st.columns([1.8, 1])

    # 1. RIGHT SECTION - PATIENT PROFILE
    with col_dash:
        st.markdown('<div style="text-align: center; padding: 20px;"><h2 style="color: #6366f1; font-family: \'Outfit\', sans-serif;">🏥 Patient Dashboard</h2></div>', unsafe_allow_html=True)
        det = st.session_state["appointment_details"]
        
        # Display Cards
        st.markdown(f'''
            <div class="dashboard-item" style="color: white; padding: 15px;">
                <div style="font-size: 0.75rem; color: #94a3b8; text-transform: uppercase;">Patient Name</div>
                <div style="font-size: 1.1rem; font-weight: 600; color: #ffffff;">{det.get("name", "---")}</div>
            </div>
            <div class="dashboard-item" style="color: white; padding: 15px;">
                <div style="font-size: 0.75rem; color: #94a3b8; text-transform: uppercase;">Patient Email</div>
                <div style="font-size: 0.95rem; font-weight: 500; color: #ffffff; word-break: break-all;">{det.get("email", "---")}</div>
            </div>
        ''', unsafe_allow_html=True)
        
        sc1, sc2 = st.columns(2)
        with sc1: st.markdown(f'<div class="dashboard-item" style="padding: 12px; color: white;"><div style="font-size: 0.7rem; color: #94a3b8; text-transform: uppercase;">Age</div><div style="color: white;">{det.get("age", "--")}</div></div>', unsafe_allow_html=True)
        with sc2: st.markdown(f'<div class="dashboard-item" style="padding: 12px; color: white;"><div style="font-size: 0.7rem; color: #94a3b8; text-transform: uppercase;">Gender</div><div style="color: white;">{det.get("gender", "--")}</div></div>', unsafe_allow_html=True)
        
        st.markdown(f'<div class="dashboard-item" style="border-left-color: #818cf8; color: white;"><div style="font-size: 0.8rem; color: #94a3b8; text-transform: uppercase;">Medical Specialist</div><div style="color: #a5b4fc; font-weight: 600;">{det.get("selected_doctor", "Awaiting Analysis...")}</div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="dashboard-item" style="color: white;"><div style="font-size: 0.8rem; color: #94a3b8; text-transform: uppercase;">Appointment</div><div style="color: white;">📅 {det.get("appointment_date", "Not Set")}</div><div style="color: white;">🕒 {det.get("appointment_time", "Not Set")}</div></div>', unsafe_allow_html=True)
        
        if st.button("Reset Session", use_container_width=True):
            st.session_state["messages"] = []; st.session_state["appointment_details"] = {}; st.session_state["step"] = None; st.rerun()

    with col_chat:
        # 2. CHAT HISTORY
        for m in st.session_state["messages"]:
            avatar = "🤖" if m["role"] == "assistant" else "👤"
            with st.chat_message(m["role"], avatar=avatar): st.write(m["content"])

        # 3. INITIAL GREETING (If app just started)
        if st.session_state["step"] is None and not st.session_state["messages"]:
            welcome_msg = "Welcome! I'm your Medical Assistant. How can I help you today?"
            options_msg = "1. Book Appointment\n2. Reschedule\n3. Cancel\n4. Medical Info\n5. Exit"
            st.session_state["messages"].append({"role": "assistant", "content": welcome_msg})
            st.session_state["messages"].append({"role": "assistant", "content": options_msg})
            st.session_state["step"] = "options"
            st.session_state["to_speak"] = welcome_msg + ". " + options_msg
            st.rerun()

        # 4. VOICE COMPONENT (ALWAYS ABOVE CHAT INPUT)
        with st.container():
            st.markdown("""
                <div style="background: rgba(31, 41, 55, 0.3); padding: 15px; border-radius: 20px; border: 1px solid rgba(99, 102, 241, 0.2); margin-top: 10px; margin-bottom: 5px;">
                    <div style="color: #a5b4fc; font-size: 0.85rem; font-weight: 600; text-align: center; margin-bottom: 8px;">🎙️ VOICE COMMANDS</div>
                    <div style="color: #94a3b8; font-size: 0.75rem; text-align: center; line-height: 1.4;">
                        Click <b>Record</b>, speak clearly, and click <b>Stop</b> to send.<br>
                        "I want to book", "My name is...", "I have a headache"
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            audio = mic_recorder(
                start_prompt="🔴 Start Recording", 
                stop_prompt="✅ Stop & Process", 
                key=f"rec_{st.session_state['audio_key_index']}",
                use_container_width=True
            )
            
            if audio:
                curr_aid = hashlib.md5(audio['bytes']).hexdigest()
                if st.session_state.get("last_audio_id") != curr_aid:
                    with st.spinner("Analyzing your voice..."):
                        txt = voice_utils.transcribe_audio(audio['bytes'])
                        if txt:
                            st.session_state["pending_input"] = txt
                            st.session_state["last_audio_id"] = curr_aid
                            st.session_state["audio_key_index"] += 1
                            st.rerun()

        # 5. INPUT HANDLING
        user_input = st.chat_input("Type or say anything...")
        if st.session_state.get("pending_input"):
            user_input = st.session_state.pop("pending_input")

    if user_input:
        step = st.session_state["step"]
        # --- SMART AI EXTRACTION ---
        if step not in [None, "options", "medical_info"] and is_complex_input(user_input, step):
             with st.spinner("AI is understanding..."):
                extracted = symptom_analyzer.extract_entities(user_input)
                if extracted:
                    for k, v in extracted.items():
                        if v and not st.session_state["appointment_details"].get(k):
                            if k == "email": v = str(v).lower().replace(" ", "").strip()
                            st.session_state["appointment_details"][k] = v

        # --- STEP HANDLER ---
        if step == "options":
            n = normalize_input(user_input)
            if n == "1": st.session_state["step"] = get_next_missing_field(); ask_step_question(st.session_state["step"]); st.rerun()
            elif n == "2": st.session_state["step"] = "reschedule_email"; ask_step_question("email"); st.rerun()
            elif n == "3": st.session_state["step"] = "cancel_email"; ask_step_question("email"); st.rerun()
            elif n == "4": st.session_state["step"] = "medical_info"; st.session_state["messages"].append({"role": "assistant", "content": "What disease?"}); st.rerun()
            elif n == "5": st.session_state["messages"].append({"role": "assistant", "content": "Goodbye!"}); st.session_state["step"] = None
        elif step == "name":
            st.session_state["appointment_details"]["name"] = user_input
            st.session_state["step"] = get_next_missing_field(); ask_step_question(st.session_state["step"]); st.rerun()
        elif step == "email":
            st.session_state["appointment_details"]["email"] = user_input.lower().replace(" ", "").strip()
            st.session_state["step"] = get_next_missing_field(); ask_step_question(st.session_state["step"]); st.rerun()
        elif step == "mobile":
            c = re.sub(r'\D', '', user_input)
            if validate_mobile(c): st.session_state["appointment_details"]["mobile"] = c; st.session_state["step"] = get_next_missing_field(); ask_step_question(st.session_state["step"]); st.rerun()
            else: st.error("Invalid mobile number.")
        elif step == "age":
            c = re.sub(r'\D', '', user_input)
            if c.isdigit(): st.session_state["appointment_details"]["age"] = c; st.session_state["step"] = get_next_missing_field(); ask_step_question(st.session_state["step"]); st.rerun()
        elif step == "gender":
            g = user_input.lower()
            res = "Male" if "mal" in g or "mail" in g else "Female" if "fem" in g else "Transgender" if "trans" in g else None
            if res: st.session_state["appointment_details"]["gender"] = res; st.session_state["step"] = get_next_missing_field(); ask_step_question(st.session_state["step"]); st.rerun()
        elif step == "symptoms":
            s = user_input; st.session_state["appointment_details"]["symptoms"] = s
            with st.spinner("Analyzing..."):
                ana = symptom_analyzer.analyze_symptom(s)
                spec = ana["specialty"]
                st.session_state["messages"].append({"role": "assistant", "content": f"Recommended Specialty: **{spec}**\n\n{ana['reasoning']}"})
                docs = doctors_by_specialty.get(spec, ["General Doctor"])[:5]
                st.session_state["appointment_details"]["docs"] = docs
                st.session_state["step"] = "select_doctor"
                sel_msg = "Select doctor:\n" + "\n".join([f"{i+1}. {d}" for i, d in enumerate(docs)])
                st.session_state["messages"].append({"role": "assistant", "content": sel_msg})
                st.session_state["to_speak"] = sel_msg
                st.rerun()
        elif step == "select_doctor":
            docs = st.session_state["appointment_details"].get("docs", [])
            idx = None
            norm = normalize_input(user_input)
            if norm.isdigit():
                i = int(norm) - 1
                if 0 <= i < len(docs): idx = i
            if idx is None:
                user_low = user_input.lower()
                for i, d in enumerate(docs):
                    if d.lower() in user_low or user_low in d.lower().replace("dr. ", ""):
                        idx = i
                        break
            if idx is not None:
                st.session_state["appointment_details"]["selected_doctor"] = docs[idx]
                st.session_state["step"] = get_next_missing_field(); ask_step_question(st.session_state["step"]); st.rerun()
            else: st.error(f"Please say the number (1-{len(docs)}) or the doctor's name.")
        elif step == "appointment_date":
            d = parse_date(user_input)
            if not d:
                res = symptom_analyzer.parse_datetime_ai(user_input, f"Today is {datetime.now().strftime('%Y-%m-%d')}")
                if res and res.get("date"): d = res["date"]
            if d and not is_past_date(d): st.session_state["appointment_details"]["appointment_date"] = d; st.session_state["step"] = get_next_missing_field(); ask_step_question(st.session_state["step"]); st.rerun()
        elif step == "appointment_time":
            t = parse_time(user_input)
            if not t:
                res = symptom_analyzer.parse_datetime_ai(user_input, f"Now is {datetime.now().strftime('%I:%M %p')}")
                if res and res.get("time"): t = res["time"]
            if t:
                date = st.session_state["appointment_details"]["appointment_date"]
                if not is_past_time(date, t): st.session_state["appointment_details"]["appointment_time"] = t; st.session_state["step"] = "confirm_appointment"; ask_step_question("confirm_appointment"); st.rerun()
        elif step == "confirm_appointment":
            if normalize_input(user_input) in ["1", "yes", "confirm"]:
                d = st.session_state["appointment_details"]
                res = database.add_appointment(d["email"], d["name"], d["mobile"], int(d["age"]), d["gender"], d["symptoms"], d["selected_doctor"], d["appointment_date"], d["appointment_time"])
                id_str = f"APPT-{res.data[0]['id']}" if res and res.data and res.data[0].get('id') else "OK"
                email_body = f"""Hello {d['name']}, your appointment has been booked. Details: ID {id_str}, Doctor {d['selected_doctor']}, Date {d['appointment_date']}, Time {d['appointment_time']}."""
                send_email(d["email"], f"Appointment Confirmation - {id_str}", email_body)
                msg = f"Booked successfully! ID: {id_str}. Confirmation sent to your email."
                st.session_state["messages"].append({"role": "assistant", "content": msg})
                st.session_state["to_speak"] = msg
                st.session_state["step"] = None; st.session_state["appointment_details"] = {}; st.rerun()
            else:
                msg = "Appointment booking cancelled. How else can I help you today?"
                st.session_state["messages"].append({"role": "assistant", "content": msg})
                st.session_state["to_speak"] = msg
                st.session_state["step"] = None; st.session_state["appointment_details"] = {}; st.rerun()
        elif step == "reschedule_email":
            email_val = user_input.lower().replace(" ", "").strip()
            appts = database.get_appointments(email_val)
            if not appts:
                msg = f"No appointments found for '{email_val}'. Type '1' to book an appointment or ask another question."
                st.session_state["messages"].append({"role": "assistant", "content": msg})
                st.session_state["to_speak"] = msg
                st.session_state["step"] = None
                st.rerun()
            else:
                st.session_state["reschedule_appts"] = appts
                list_str = "\n".join([f"{i+1}. Dr. {a.get('doctor')} on {a.get('appointment_date')} at {a.get('appointment_time')} (ID: {a.get('id')})" for i, a in enumerate(appts)])
                msg = f"Found {len(appts)} appointment(s):\n{list_str}\n\nPlease enter the number of the appointment you want to reschedule:"
                st.session_state["messages"].append({"role": "assistant", "content": msg})
                st.session_state["to_speak"] = msg
                st.session_state["step"] = "reschedule_pick"
                st.rerun()
        elif step == "reschedule_pick":
            appts = st.session_state.get("reschedule_appts", [])
            norm = normalize_input(user_input)
            idx = int(norm) - 1 if norm.isdigit() else -1
            if 0 <= idx < len(appts):
                st.session_state["target_reschedule_appt"] = appts[idx]
                msg = f"Selected appointment with Dr. {appts[idx].get('doctor')}. What is your new preferred date? (e.g. YYYY-MM-DD or 'tomorrow')"
                st.session_state["messages"].append({"role": "assistant", "content": msg})
                st.session_state["to_speak"] = msg
                st.session_state["step"] = "reschedule_new_date"
                st.rerun()
            else:
                st.error(f"Please choose a valid number between 1 and {len(appts)}.")
        elif step == "reschedule_new_date":
            d = parse_date(user_input)
            if not d:
                res = symptom_analyzer.parse_datetime_ai(user_input, f"Today is {datetime.now().strftime('%Y-%m-%d')}")
                if res and res.get("date"): d = res["date"]
            if d and not is_past_date(d):
                st.session_state["new_reschedule_date"] = d
                msg = "What time would you prefer? (e.g. 11:00 AM)"
                st.session_state["messages"].append({"role": "assistant", "content": msg})
                st.session_state["to_speak"] = msg
                st.session_state["step"] = "reschedule_new_time"
                st.rerun()
            else:
                st.error("Please enter a valid future date (e.g., 2026-09-10 or tomorrow).")
        elif step == "reschedule_new_time":
            t = parse_time(user_input)
            if not t:
                res = symptom_analyzer.parse_datetime_ai(user_input, f"Now is {datetime.now().strftime('%I:%M %p')}")
                if res and res.get("time"): t = res["time"]
            if t:
                target = st.session_state.get("target_reschedule_appt", {})
                new_d = st.session_state.get("new_reschedule_date")
                appt_id = target.get("id")
                database.reschedule_appointment(appt_id, new_d, t)
                msg = f"✅ Appointment ID {appt_id} has been successfully rescheduled to {new_d} at {t}!"
                st.session_state["messages"].append({"role": "assistant", "content": msg})
                st.session_state["to_speak"] = msg
                st.session_state["step"] = None
                st.session_state.pop("target_reschedule_appt", None)
                st.session_state.pop("reschedule_appts", None)
                st.rerun()
            else:
                st.error("Please enter a valid time (e.g., 10:30 AM).")
        elif step == "cancel_email":
            email_val = user_input.lower().replace(" ", "").strip()
            appts = database.get_appointments(email_val)
            if not appts:
                msg = f"No appointments found for '{email_val}'."
                st.session_state["messages"].append({"role": "assistant", "content": msg})
                st.session_state["to_speak"] = msg
                st.session_state["step"] = None
                st.rerun()
            else:
                st.session_state["cancel_appts"] = appts
                list_str = "\n".join([f"{i+1}. Dr. {a.get('doctor')} on {a.get('appointment_date')} at {a.get('appointment_time')} (ID: {a.get('id')})" for i, a in enumerate(appts)])
                msg = f"Found {len(appts)} appointment(s):\n{list_str}\n\nPlease enter the number of the appointment you wish to cancel:"
                st.session_state["messages"].append({"role": "assistant", "content": msg})
                st.session_state["to_speak"] = msg
                st.session_state["step"] = "cancel_pick"
                st.rerun()
        elif step == "cancel_pick":
            appts = st.session_state.get("cancel_appts", [])
            norm = normalize_input(user_input)
            idx = int(norm) - 1 if norm.isdigit() else -1
            if 0 <= idx < len(appts):
                target = appts[idx]
                appt_id = target.get("id")
                database.cancel_appointment(appt_id)
                msg = f"🗑️ Appointment ID {appt_id} with Dr. {target.get('doctor')} has been cancelled."
                st.session_state["messages"].append({"role": "assistant", "content": msg})
                st.session_state["to_speak"] = msg
                st.session_state["step"] = None
                st.session_state.pop("cancel_appts", None)
                st.rerun()
            else:
                st.error(f"Please choose a valid number between 1 and {len(appts)}.")
        elif step == "medical_info":
            with st.spinner("Consulting AI medical knowledge..."):
                ana = symptom_analyzer.analyze_symptom(user_input)
                spec = ana.get("specialty", "Primary Care Doctor")
                msg = f"For '{user_input}', consulting a **{spec}** is recommended.\n\n*Reasoning:* {ana.get('reasoning', 'General evaluation recommended.')}\n\n*Note: This is AI assistance and not a substitute for professional medical diagnosis.* Type '1' to book an appointment with a specialist."
                st.session_state["messages"].append({"role": "assistant", "content": msg})
                st.session_state["to_speak"] = msg
                st.session_state["step"] = None
                st.rerun()

def main():
    st.set_page_config(page_title="Medical Assistant", page_icon="🏥", initial_sidebar_state="collapsed", layout="wide")
    inject_custom_css()
    st.markdown('<div class="title">✨ Advanced AI Medical Assistant</div>', unsafe_allow_html=True)
    handle_chat()
    if "to_speak" in st.session_state and st.session_state["to_speak"]:
        text_to_say = st.session_state.pop("to_speak")
        speak_text(text_to_say)

if __name__ == "__main__":
    main()
