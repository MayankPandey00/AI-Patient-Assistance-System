import io
import os
import sqlite3
import requests
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv
from urllib.parse import quote

load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip()

# Initialize Google GenAI SDK if key is provided
GENINI_ENABLED = False
if GEMINI_API_KEY:
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        GENINI_ENABLED = True
    except ImportError:
        print("Google GenAI SDK not installed properly.")

# Synopsis-specified libraries
import speech_recognition as sr
from gtts import gTTS
from cryptography.fernet import Fernet

try:
    import mysql.connector
    MYSQL_INSTALLED = True
except ImportError:
    MYSQL_INSTALLED = False

app = Flask(__name__)

from modules.auth import init_auth, translator_access_required, full_login_required

# Add this right after `app = Flask(__name__)`
init_auth(app, db_path="medical_data_repository.db")  # Change if your app uses medical_repository.db


CORS(app)
http_session = requests.Session()
# ==============================================================================
# MODULE 5: DATA SECURITY MODULE (Fernet Encryption)
# ==============================================================================
KEY_FILE = "medical_secret.key"
if os.path.exists(KEY_FILE):
    with open(KEY_FILE, "rb") as f:
        SECRET_KEY = f.read()
else:
    SECRET_KEY = Fernet.generate_key()
    with open(KEY_FILE, "wb") as f:
        f.write(SECRET_KEY)

cipher_suite = Fernet(SECRET_KEY)
AUTHORISED_STAFF_PIN = "1234"

def encrypt_data(plain_text: str) -> str:
    return cipher_suite.encrypt(plain_text.encode("utf-8")).decode("utf-8")

def decrypt_data(encrypted_text: str) -> str:
    try:
        return cipher_suite.decrypt(encrypted_text.encode("utf-8")).decode("utf-8")
    except Exception:
        return "[Encrypted Medical Record]"


# ==============================================================================
# MODULE 6: DATABASE MODULE (SQLite Repository + MySQL Support)
# ==============================================================================
SQLITE_DB = "medical_data_repository.db"

def init_databases():
    conn = sqlite3.connect(SQLITE_DB)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medical_records (
            record_id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT NOT NULL,
            speaker_role TEXT NOT NULL,
            source_language TEXT NOT NULL,
            target_language TEXT NOT NULL,
            encrypted_original_text TEXT NOT NULL,
            encrypted_translated_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_databases()

def store_medical_interaction(patient_id: str, speaker_role: str, src_lang: str, target_lang: str, orig_text: str, trans_text: str):
    enc_orig = encrypt_data(orig_text)
    enc_trans = encrypt_data(trans_text)

    conn = sqlite3.connect(SQLITE_DB)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO medical_records 
        (patient_id, speaker_role, source_language, target_language, encrypted_original_text, encrypted_translated_text)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (patient_id, speaker_role, src_lang, target_lang, enc_orig, enc_trans))
    conn.commit()
    conn.close()

def retrieve_patient_history(patient_id: str) -> list:
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM medical_records WHERE patient_id = ? ORDER BY record_id DESC", (patient_id,))
    rows = cursor.fetchall()
    conn.close()

    return [{
        "record_id": r["record_id"],
        "patient_id": r["patient_id"],
        "speaker_role": r["speaker_role"],
        "source_language": r["source_language"],
        "target_language": r["target_language"],
        "original_text": decrypt_data(r["encrypted_original_text"]),
        "translated_text": decrypt_data(r["encrypted_translated_text"]),
        "created_at": r["created_at"]
    } for r in rows]


# ==============================================================================
# MODULE 2: SPEECH-TO-TEXT MODULE
# ==============================================================================
STT_LANGUAGE_CODES = {
    "hi": "hi-IN", "bn": "bn-IN", "ta": "ta-IN", "te": "te-IN",
    "mr": "mr-IN", "gu": "gu-IN", "pa": "pa-IN", "kn": "kn-IN",
    "ml": "ml-IN", "en": "en-IN"
}

def convert_voice_to_text(wav_bytes_io: io.BytesIO, lang_code: str) -> tuple:
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(wav_bytes_io) as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)
            audio_data = recognizer.record(source)

        locale = STT_LANGUAGE_CODES.get(lang_code, "en-IN")
        
        # Dynamically access recognize_google so Pylance shows 0 errors
        recognize_fn = getattr(recognizer, "recognize_google")
        text = recognize_fn(audio_data, language=locale)
        return True, str(text)
    except sr.UnknownValueError:
        return False, "Speech could not be understood clearly. Please speak closer to the microphone."
    except sr.RequestError as e:
        return False, f"Speech Recognition API service error: {str(e)}"
    except Exception as e:
        return False, f"Speech recognition error: {str(e)}"


# ==============================================================================
# MODULE 3: LANGUAGE TRANSLATION MODULE (Powered by your Gemini API Key)
# ==============================================================================
LANGUAGE_NAMES = {
    "hi": "Hindi", "bn": "Bengali", "ta": "Tamil", "te": "Telugu",
    "mr": "Marathi", "gu": "Gujarati", "pa": "Punjabi", "kn": "Kannada",
    "ml": "Malayalam", "es": "Spanish", "en": "English"
}

# def translate_medical_text(text: str, src_lang: str, target_lang: str, speaker_role: str = "PATIENT") -> str:
#     if not text or src_lang == target_lang:
#         return text

#     src_name = LANGUAGE_NAMES.get(src_lang, src_lang)
#     target_name = LANGUAGE_NAMES.get(target_lang, target_lang)

#     # -------------------------------------------------------------
#     # TIER 1: Try your Gemini API Key
#     # -------------------------------------------------------------
#     if GENINI_ENABLED:
#         try:
#             system_prompt = (
#                 f"You are an expert hospital medical interpreter translating statements from {src_name} to {target_name}. "
#                 f"The speaker is a {speaker_role}. Preserve precise clinical accuracy, symptoms, medication dosages, "
#                 f"and medical terminology. Output ONLY the translated text in {target_name} without conversational filler."
#             )
#             response = client.models.generate_content(
#                 model=GEMINI_MODEL,
#                 contents=f"{system_prompt}\n\nText to translate: {text}"
#             )
#             if response and response.text:
#                 result = response.text.strip()
#                 print(f"✅ [Gemini API Translation Success]: {result}")
#                 return result
#         except Exception as e:
#             print(f"⚠️ [Gemini API failed, switching to Fallback 1]: {e}")

#     # -------------------------------------------------------------
#     # TIER 2: Google GTX Engine (with browser User-Agent header)
#     # -------------------------------------------------------------
#     try:
#         url = "https://translate.googleapis.com/translate_a/single"
#         headers = {
#             "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
#         }
#         params = {
#             "client": "gtx",
#             "sl": src_lang,
#             "tl": target_lang,
#             "dt": "t",
#             "q": text
#         }
#         resp = http_session.get(url, params=params, headers=headers, timeout=5)
#         if resp.status_code == 200:
#             data = resp.json()
#             translated = "".join([segment[0] for segment in data[0] if segment and segment[0]])
#             if translated:
#                 print(f"⚡ [GTX Translation Success]: {translated}")
#                 return translated
#         else:
#             print(f"⚠️ [GTX returned status {resp.status_code}]")
#     except Exception as e:
#         print(f"⚠️ [GTX Engine failed, switching to Fallback 2]: {e}")

#     # -------------------------------------------------------------
#     # TIER 3: MyMemory Translation API (Backup)
#     # -------------------------------------------------------------
#     try:
#         url2 = "https://api.mymemory.translated.net/get"
#         resp2 = http_session.get(
#             url2,
#             params={"q": text, "langpair": f"{src_lang}|{target_lang}"},
#             timeout=5
#         )
#         if resp2.status_code == 200:
#             translated = resp2.json().get("responseData", {}).get("translatedText", "")
#             if translated and not translated.startswith("MYMEMORY WARNING"):
#                 print(f"🌐 [MyMemory Translation Success]: {translated}")
#                 return translated
#     except Exception as e:
#         print(f"⚠️ [MyMemory Engine failed]: {e}")

#     # If all tiers fail, return the original text with a warning
#     print("❌ All translation engines failed. Please check internet connection.")
#     return text


def translate_medical_text(text: str, src_lang: str, target_lang: str, speaker_role: str = "PATIENT") -> str:
    if not text or src_lang == target_lang:
        return text

    src_name = LANGUAGE_NAMES.get(src_lang, src_lang)
    target_name = LANGUAGE_NAMES.get(target_lang, target_lang)

    # -------------------------------------------------------------
    # TIER 1: Gemini API
    # -------------------------------------------------------------
    if GENINI_ENABLED:
        try:
            system_prompt = (
                f"You are an expert hospital medical interpreter translating statements into {target_name}. "
                f"The speaker is a {speaker_role} (expected source language: {src_name}, including phonetic/romanized text). "
                f"Preserve precise clinical accuracy, symptoms, medication dosages, and medical terminology. "
                f"Output ONLY the translated text in {target_name} without conversational filler."
            )
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=f"{system_prompt}\n\nText to translate: {text}"
            )
            if response and response.text:
                result = response.text.strip()
                print(f"[Gemini Translation Success]: {result}", flush=True)
                return result
        except Exception as e:
            print(f"[Gemini API failed]: {e}", flush=True)
    else:
        print("[Gemini API skipped]: GEMINI_API_KEY missing or google-genai not installed", flush=True)

    # -------------------------------------------------------------
    # TIER 2: Google GTX Engine (auto-detect source language)
    # -------------------------------------------------------------
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": target_lang,
            "dt": "t",
            "q": text
        }
        resp = http_session.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            translated = "".join([segment[0] for segment in data[0] if segment and segment[0]])
            if translated:
                print(f"[GTX Translation Success]: {translated}", flush=True)
                return translated
        else:
            print(f"[GTX failed]: HTTP {resp.status_code}", flush=True)
    except Exception as e:
        print(f"[GTX Engine failed]: {e}", flush=True)

    # -------------------------------------------------------------
    # TIER 3: MyMemory Translation API (Backup)
    # -------------------------------------------------------------
    try:
        url2 = "https://api.mymemory.translated.net/get"
        resp2 = http_session.get(
            url2,
            params={"q": text, "langpair": f"{src_lang}|{target_lang}"},
            timeout=10
        )
        if resp2.status_code == 200:
            translated = resp2.json().get("responseData", {}).get("translatedText", "")
            if translated and not translated.startswith("MYMEMORY WARNING"):
                print(f"[MyMemory Translation Success]: {translated}", flush=True)
                return translated
            print(f"[MyMemory skipped]: {translated}", flush=True)
        else:
            print(f"[MyMemory failed]: HTTP {resp2.status_code}", flush=True)
    except Exception as e:
        print(f"[MyMemory Engine failed]: {e}", flush=True)

    raise RuntimeError("All translation engines failed. Check Render Logs for Gemini/GTX/MyMemory errors.")

    
# ==============================================================================
# MODULE 4: RESPONSE GENERATION MODULE (gTTS)
# ==============================================================================
@app.route("/api/tts", methods=["GET"])
@translator_access_required
def generate_tts_response():
    text = (request.args.get("text") or "").strip()
    lang = (request.args.get("lang") or "en").strip()
    if not text:
        return "No text provided", 400

    try:
        audio_buffer = io.BytesIO()
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        return send_file(audio_buffer, mimetype="audio/mpeg", as_attachment=False)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==============================================================================
# FLASK API PIPELINE ROUTES
# ==============================================================================
# @app.route("/")
# def home():
#     return render_template("index.html")

@app.route("/")
@translator_access_required
def index():
    return render_template("index.html")

@app.route("/api/voice-pipeline", methods=["POST"])
@translator_access_required
def process_voice_pipeline():
    if "audio" not in request.files:
        return jsonify({"success": False, "error": "No voice recording received."}), 400

    audio_file = request.files["audio"]
    speaker_role = request.form.get("speaker_role", "PATIENT")
    src_lang = request.form.get("src_lang", "hi")
    target_lang = request.form.get("target_lang", "en")
    patient_id = request.form.get("patient_id", "PT-101")

    wav_io = io.BytesIO(audio_file.read())

    stt_success, recognized_text = convert_voice_to_text(wav_io, src_lang)
    if not stt_success:
        return jsonify({"success": False, "error": recognized_text}), 400

    # --- WRAPPED TRANSLATION CALL ---
    try:
        translated_text = translate_medical_text(recognized_text, src_lang, target_lang, speaker_role)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 502

    store_medical_interaction(patient_id, speaker_role, src_lang, target_lang, recognized_text, translated_text)

    return jsonify({
        "success": True,
        "original_text": recognized_text,
        "translated_text": translated_text,
        "tts_url": f"/api/tts?text={quote(translated_text)}&lang={target_lang}"
    })

@app.route("/api/text-pipeline", methods=["POST"])
@translator_access_required
def process_text_pipeline():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    speaker_role = data.get("speaker_role", "PATIENT")
    src_lang = data.get("src_lang", "hi")
    target_lang = data.get("target_lang", "en")
    patient_id = data.get("patient_id", "PT-101")

    if not text:
        return jsonify({"success": False, "error": "Please enter or speak a message."}), 400

    # --- WRAPPED TRANSLATION CALL ---
    try:
        translated_text = translate_medical_text(text, src_lang, target_lang, speaker_role)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 502

    store_medical_interaction(patient_id, speaker_role, src_lang, target_lang, text, translated_text)

    return jsonify({
        "success": True,
        "original_text": text,
        "translated_text": translated_text,
        "tts_url": f"/api/tts?text={quote(translated_text)}&lang={target_lang}"
    })

@app.route("/api/history", methods=["POST"])
@full_login_required
def get_history():
    data = request.get_json(silent=True) or {}
    patient_id = data.get("patient_id", "PT-101")
    staff_pin = data.get("staff_pin", "1234")

    if staff_pin != AUTHORISED_STAFF_PIN:
        return jsonify({"success": False, "error": "Unauthorised Access! Invalid Hospital Staff PIN."}), 403

    records = retrieve_patient_history(patient_id)
    return jsonify({"success": True, "records": records})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("===================================================================")
    print(" AI-BASED MULTILINGUAL PATIENT ASSISTANCE SYSTEM")
    print(f" Gemini API Status: {'ACTIVE (Model: ' + GEMINI_MODEL + ')' if GENINI_ENABLED else 'INACTIVE (Using Fallback)'}")
    print(f" Running on port {port}")
    print("===================================================================")
    app.run(host="0.0.0.0", port=port, debug=False)