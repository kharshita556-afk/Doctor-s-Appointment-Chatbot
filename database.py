import os
import sqlite3
from datetime import datetime
import streamlit as st
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables (Local)
load_dotenv()

LOCAL_DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_appointments.db")

def init_local_db():
    """Initializes local SQLite database fallback."""
    try:
        conn = sqlite3.connect(LOCAL_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                name TEXT,
                mobile TEXT,
                age INTEGER,
                gender TEXT,
                symptoms TEXT,
                doctor TEXT,
                appointment_date TEXT,
                appointment_time TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error initializing local DB: {e}")

# Initialize local DB on load
init_local_db()

class MockResponse:
    """Mock Supabase response object for fallback database operations."""
    def __init__(self, data):
        self.data = data

def get_secret(key, default=None):
    """Robustly fetch secrets from Streamlit or Environment."""
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)

def clean_credential(val):
    """Clean and sanitize secret values to prevent whitespace or quote issues."""
    if not val:
        return None
    val = str(val).strip().strip('"\'')
    return val if val else None

raw_url = clean_credential(get_secret("SUPABASE_URL"))
raw_key = clean_credential(get_secret("SUPABASE_KEY"))

if raw_url:
    raw_url = raw_url.rstrip('/')
    if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
        raw_url = f"https://{raw_url}"

url = raw_url
key = raw_key

# Create client only if credentials are found
supabase: Client = None
if url and key:
    try:
        supabase = create_client(url, key)
    except Exception as e:
        print(f"Error initializing Supabase client: {e}")
        supabase = None

_supabase_operational = False

def test_connection():
    """
    Tests the connection to the Supabase appointments table.
    Returns (is_connected: bool, message: str).
    Provides friendly diagnostic advice if the Supabase project is paused or malformed.
    """
    global _supabase_operational
    if not supabase or not url or not key:
        _supabase_operational = False
        return False, "Supabase credentials (SUPABASE_URL / SUPABASE_KEY) are not configured. Running in Local Fallback Mode."
    
    try:
        supabase.table("appointments").select("id").limit(1).execute()
        _supabase_operational = True
        return True, None
    except Exception as e:
        _supabase_operational = False
        err_msg = str(e)
        
        # Diagnose DNS resolution error (project paused or bad URL)
        if "-2" in err_msg or "Name or service not known" in err_msg or "gaierror" in err_msg.lower() or "connecterror" in err_msg.lower():
            diagnostic = (
                f"Cannot resolve Supabase hostname ({url}). "
                "Your Supabase Free Tier project is likely PAUSED due to inactivity. "
                "Log into your Supabase Dashboard and click 'Restore project' to resume cloud sync."
            )
            return False, diagnostic
        
        # Diagnose table missing or RLS blocking
        if "PGRST205" in err_msg or "does not exist" in err_msg.lower() or "schema cache" in err_msg.lower():
            diagnostic = (
                "Connected to Supabase, but the 'appointments' table was not found or is blocked by RLS. "
                "Please verify your table exists in Supabase Table Editor."
            )
            return False, diagnostic
            
        # Diagnose authentication failure
        if "401" in err_msg or "unauthorized" in err_msg.lower() or "jwt" in err_msg.lower() or "invalid api key" in err_msg.lower():
            diagnostic = (
                "Supabase authentication failed. Please verify that SUPABASE_KEY in Streamlit Secrets is the valid anon/public key."
            )
            return False, diagnostic

        return False, err_msg

def is_supabase_active():
    """Check if Supabase is currently connected and operational."""
    return _supabase_operational

def add_appointment(email, name, mobile, age, gender, symptoms, doctor, date, time):
    """Adds a new appointment to Supabase, falling back to SQLite if unreachable."""
    data = {
        "email": email,
        "name": name,
        "mobile": mobile,
        "age": age,
        "gender": gender,
        "symptoms": symptoms,
        "doctor": doctor,
        "appointment_date": date,
        "appointment_time": time,
    }
    
    # 1. Try Supabase first if available
    if supabase and _supabase_operational:
        try:
            response = supabase.table("appointments").insert(data).execute()
            if response and response.data:
                return response
        except Exception as e:
            print(f"Supabase add_appointment failed: {e}. Falling back to local storage.")
    
        try:
            safe_age = int(age)
        except (ValueError, TypeError):
            safe_age = 0
        conn = sqlite3.connect(LOCAL_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO appointments (email, name, mobile, age, gender, symptoms, doctor, appointment_date, appointment_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (email, name, mobile, safe_age, gender, symptoms, doctor, date, time))
        conn.commit()
        row_id = cursor.lastrowid
        conn.close()
        return MockResponse([{"id": row_id, **data}])
    except Exception as e:
        print(f"Local DB add_appointment error: {e}")
        return MockResponse([{"id": 1, **data}])

def get_appointments(email):
    """Fetches appointments for a specific user email."""
    normalized_email = (email or "").strip().lower()
    
    # 1. Try Supabase
    if supabase and _supabase_operational:
        try:
            response = supabase.table("appointments").select("*").ilike("email", normalized_email).execute()
            if response and response.data is not None:
                return response.data
        except Exception as e:
            print(f"Supabase get_appointments failed: {e}. Reading from local storage.")
    
    # 2. Fallback to Local SQLite DB
    try:
        conn = sqlite3.connect(LOCAL_DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM appointments WHERE LOWER(email) = ? ORDER BY id DESC", (normalized_email,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"Local DB get_appointments error: {e}")
        return []

def cancel_appointment(appointment_id):
    """Cancels an appointment by its unique ID."""
    # 1. Try Supabase
    if supabase and _supabase_operational:
        try:
            response = supabase.table("appointments").delete().eq("id", appointment_id).execute()
            if response:
                return response
        except Exception as e:
            print(f"Supabase cancel_appointment failed: {e}. Removing from local storage.")
            
    # 2. Local SQLite DB
    try:
        conn = sqlite3.connect(LOCAL_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM appointments WHERE id = ?", (appointment_id,))
        conn.commit()
        conn.close()
        return MockResponse([{"id": appointment_id}])
    except Exception as e:
        print(f"Local DB cancel_appointment error: {e}")
        return None

def reschedule_appointment(appointment_id, new_date, new_time):
    """Reschedules an appointment by ID."""
    # 1. Try Supabase
    if supabase and _supabase_operational:
        try:
            update_data = {
                "appointment_date": new_date,
                "appointment_time": new_time
            }
            supabase.table("appointments").update(update_data).eq("id", appointment_id).execute()
            return True
        except Exception as e:
            print(f"Supabase reschedule_appointment failed: {e}. Updating local storage.")

    # 2. Local SQLite DB
    try:
        conn = sqlite3.connect(LOCAL_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE appointments 
            SET appointment_date = ?, appointment_time = ? 
            WHERE id = ?
        """, (new_date, new_time, appointment_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Local DB reschedule_appointment error: {e}")
        return False

def check_availability(date, time, doctor):
    """Checks if a time slot is available for a doctor."""
    try:
        appointments = []
        # 1. Try Supabase
        if supabase and _supabase_operational:
            try:
                response = supabase.table("appointments").select("*").eq("doctor", doctor).eq("appointment_date", date).execute()
                if response and response.data is not None:
                    appointments = response.data
            except Exception as e:
                print(f"Supabase check_availability query failed: {e}. Checking local storage.")
                appointments = []
        
        # 2. Fallback to Local SQLite DB if Supabase not used or empty
        if not appointments:
            try:
                conn = sqlite3.connect(LOCAL_DB_FILE)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM appointments WHERE doctor = ? AND appointment_date = ?", (doctor, date))
                appointments = [dict(r) for r in cursor.fetchall()]
                conn.close()
            except Exception as e:
                print(f"Local DB check_availability error: {e}")
                appointments = []

        new_time_dt = datetime.strptime(time, "%I:%M %p")
        for appt in appointments:
            booked_time = appt.get("appointment_time")
            if not booked_time:
                continue
            try:
                booked_time_dt = datetime.strptime(booked_time, "%I:%M %p")
                diff = abs((new_time_dt - booked_time_dt).total_seconds())
                # Conflict if within 20 mins
                if diff < 1200:
                    return False
            except ValueError:
                continue

        return True
    except Exception as e:
        print(f"Error checking availability: {e}")
        return True


