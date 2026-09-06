import os
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types
from groq import Groq

# Load environment variables (Local)
load_dotenv()

def get_secret(key, default=None):
    """Robustly fetch secrets from Streamlit or Environment."""
    val = None
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            val = st.secrets[key]
    except Exception:
        pass
    if not val:
        val = os.environ.get(key, default)
    if val:
        val = str(val).strip().strip('"\'')
    return val

# Configure Clients
gemini_key = get_secret("GEMINI_API_KEY")
groq_key = get_secret("GROQ_API_KEY")

gemini_client = genai.Client(api_key=gemini_key) if gemini_key else None
groq_client = Groq(api_key=groq_key) if groq_key else None

if not gemini_key or not groq_key:
    st.warning("⚠️ AI API keys missing. AI features will be limited.")

# Use Groq as primary, Gemini as secondary
GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-flash-latest"

# Available specialties (matched exactly to dataset)
SPECIALTIES = [
    "Primary Care Doctor", "Cardiologist", "Dermatologist", "Neurologist",
    "Orthopedic Surgeon", "Pediatrician", "Psychiatrist", "Ear, Nose & Throat Doctor",
    "Ophthalmologist", "Dentist", "Gastroenterologist", "Pulmonologist",
    "Urologist"
]

def analyze_symptom(user_input):
    """
    Uses Gemini AI to analyze natural language symptom descriptions
    and recommend the appropriate medical specialty.
    """
    try:
        prompt = f"""You are a medical triage assistant. Analyze the following symptom description and recommend the most appropriate medical specialty.

Available specialties: {', '.join(SPECIALTIES)}

Symptom description: "{user_input}"

Respond in this exact format:
Specialty: [specialty name from the list above]
Confidence: [High/Medium/Low]
Reasoning: [brief explanation in one sentence]

If the symptoms are unclear or too vague, recommend "Primary Care Doctor"."""

        # Try Groq first
        try:
            if not groq_client: raise Exception("Groq client not initialized")
            response = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            result_text = response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Groq failed, falling back to Gemini: {e}")
            if not gemini_client: return fallback_keyword_match(user_input)
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt
            )
            result_text = response.text.strip()

        # Parse the response
        lines = result_text.split('\n')
        specialty = None
        confidence = "Medium"
        reasoning = ""
        
        for line in lines:
            if line.startswith("Specialty:"):
                specialty = line.replace("Specialty:", "").strip()
            elif line.startswith("Confidence:"):
                confidence = line.replace("Confidence:", "").strip()
            elif line.startswith("Reasoning:"):
                reasoning = line.replace("Reasoning:", "").strip()
        
        # Validate specialty is in our list
        if specialty not in SPECIALTIES:
            specialty = "Primary Care Doctor"
        
        return {
            "specialty": specialty,
            "confidence": confidence,
            "reasoning": reasoning,
            "success": True
        }
        
    except Exception as e:
        print(f"Error in AI symptom analysis: {e}")
        # Fallback to keyword matching
        return fallback_keyword_match(user_input)

def fallback_keyword_match(user_input):
    """Fallback to simple keyword matching if AI fails"""
    symptom_map = {
        "fever": "Primary Care Doctor",
        "cough": "Pulmonologist",
        "chest pain": "Cardiologist",
        "skin": "Dermatologist",
        "eye": "Ophthalmologist",
        "tooth": "Dentist",
        "joint": "Orthopedic Surgeon",
        "stomach": "Gastroenterologist",
        "head": "Neurologist",
        "dizz": "Neurologist",
        "back": "Orthopedic Surgeon",
        "throat": "Ear, Nose & Throat Doctor",
        "ear": "Ear, Nose & Throat Doctor",
        "nose": "Ear, Nose & Throat Doctor",
        "nausea": "Gastroenterologist",
        "vomit": "Gastroenterologist",
        "anxiety": "Psychiatrist",
        "depression": "Psychiatrist",
        "child": "Pediatrician",
        "breath": "Pulmonologist",
        "urin": "Urologist",
        "heart": "Cardiologist"
    }
    
    user_lower = user_input.lower()
    for keyword, specialty in symptom_map.items():
        if keyword in user_lower:
            return {
                "specialty": specialty,
                "confidence": "Low",
                "reasoning": f"Keyword match: '{keyword}'",
                "success": False
            }
    
    return {
        "specialty": "Primary Care Doctor",
        "confidence": "Low",
        "reasoning": "No specific symptoms identified",
        "success": False
    }

def parse_datetime_ai(user_input, current_context):
    """
    Uses Gemini AI to parse natural language date/time descriptions.
    current_context: String describing the current date/time (e.g. "Today is Saturday, Jan 24, 2026, 4:30 PM")
    Returns: A dictionary with 'date' (YYYY-MM-DD) and 'time' (HH:MM AM/PM) or None.
    """
    try:
        prompt = f"""You are a date and time parsing assistant.
Current Context: {current_context}
User Input: "{user_input}"

Convert the User Input into a standard format. 
- If the user specifies a date, return it as YYYY-MM-DD.
- If the user specifies a time, return it as HH:MM AM/PM.
- If only one is specified, leave the other as null.
- Handle relative terms like "tomorrow", "next Monday", "in 2 hours", "noon", etc.

Respond ONLY with a valid JSON object:
{{"date": "YYYY-MM-DD" or null, "time": "HH:MM AM/PM" or null}}"""

        # Try Groq First
        try:
            if not groq_client: raise Exception("Groq client not initialized")
            response = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            result = response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Groq failed, falling back to Gemini: {e}")
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt
            )
            result = response.text.strip()

        import json
        # Clean up possible markdown code blocks for Gemini fallback
        if result.startswith("```json"):
            result = result.split("```json")[1].split("```")[0].strip()
        elif result.startswith("```"):
            result = result.split("```")[1].split("```")[0].strip()
            
        data = json.loads(result)
        return data
        
    except Exception as e:
        print(f"Error in AI datetime parsing: {e}")
        return None


def extract_entities(user_input):
    """
    Uses Gemini AI to extract multiple entities from a user message.
    Entities: name, email, mobile, age, gender, symptoms, date, time.
    Returns: A dictionary with found entities.
    """
    try:
        prompt = f"""You are a medical receptionist assistant. 
Extract as many of the following fields as possible from the User Input.
Fields: name, email, mobile, age, gender, symptoms, date (YYYY-MM-DD), time (HH:MM AM/PM).

Rules:
- If the user spells out a word (e.g., "R A J N I S H"), join the letters into a single word ("rajnish").
- For 'email', join spelled-out parts and convert verbalized symbols like "at", "at the rate", or "handle" to "@" and "dot" or "point" to ".".
- For 'email', normalize to lowercase and remove all internal spaces.
- For 'mobile', remove all non-digits.
- For 'age', extract only the number.
- For 'gender', normalize to "Male", "Female", or "Transgender" (handle homophones like "mail" or "female").
- For 'date', use YYYY-MM-DD.
- For 'time', use HH:MM AM/PM.
- Use null if a field is not present.

User Input: "{user_input}"

Respond ONLY with a valid JSON object."""

        # Try Groq First
        try:
            if not groq_client: raise Exception("Groq client not initialized")
            response = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            result = response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Groq failed, falling back to Gemini: {e}")
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt
            )
            result = response.text.strip()

        import json
        result = result.strip()
        # Clean up possible markdown code blocks for Gemini
        if result.startswith("```json"):
            result = result.split("```json")[1].split("```")[0].strip()
        elif result.startswith("```"):
            result = result.split("```")[1].split("```")[0].strip()
            
        data = json.loads(result)
        return data
        
    except Exception as e:
        print(f"Error in entity extraction: {e}")
        return {}
