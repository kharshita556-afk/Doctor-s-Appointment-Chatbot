# 🌐 AI Medical Assistant - Deployment Guide

This guide explains how to host your AI Medical Assistant on **Streamlit Community Cloud** (Free) so anyone can access it via a URL.

---

## 🏗️ Step 1: Prepare Your Repository
1.  **Upload to GitHub**: Create a new repository on [GitHub](https://github.com) and upload all your project files.
    *   **Files to include**: `streamlit_app.py`, `database.py`, `calendar_utils.py`, `symptom_analyzer.py`, `voice_utils.py`, `requirements.txt`, `.gitignore`, and `LICENSE`.
    *   **🚨 IMPORTANT**: Do **NOT** upload your `.env` file or `credentials.json`. These contain your private keys and are automatically excluded by `.gitignore`.
2.  **Verify `requirements.txt`**: Ensure the file exists in your repository. It tells the hosting server which libraries to install.

---

## 🚀 Step 2: Host on Streamlit Cloud
1.  Go to [share.streamlit.io](https://share.streamlit.io/) and sign in with GitHub.
2.  Click **"New app"**.
3.  Select your repository, branch (`main`), and set the Main file path to **`streamlit_app.py`**.
4.  **Before clicking Deploy**, click on **"Advanced settings..."**.

---

## 🔐 Step 3: Configure Secrets (Essential)
Streamlit Cloud uses a "Secrets" manager instead of a `.env` file. Paste your credentials into the **Secrets box** exactly in this format:

```toml
GEMINI_API_KEY = "your_gemini_key"
GROQ_API_KEY = "your_groq_key"
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_KEY = "your-anon-role-key"
```

> [!IMPORTANT]
> If you see a warning saying `SUPABASE_URL not found`, it means this step was skipped or the keys were entered incorrectly. Double-check for extra spaces or missing quotes.

*Click **Save**, then click **Deploy**!*

---

## 📦 Step 4: System Dependencies (Voice Support)
Since your app uses `pydub` and `SpeechRecognition`, Streamlit might need `ffmpeg`.
1.  Create a new file in your GitHub repo named **`packages.txt`** (exactly this name).
2.  Paste this single word inside:
    ```text
    ffmpeg
    ```
3.  Commit and push.

---

## ✅ Deployment Checklist
- [ ] Code is on GitHub.
- [ ] `requirements.txt` is present.
- [ ] `packages.txt` with `ffmpeg` is present.
- [ ] API Secrets are added in Streamlit Cloud Dashboard.
- [ ] Database (Supabase) is reachable.

---

## 🔧 Troubleshooting Common Issues

### 🚨 `Connection Error: [Errno -2] Name or service not known`
If you encounter this error on Streamlit Cloud:
1. **Supabase Inactivity Auto-Pause (Most Common)**:
   - Supabase automatically pauses Free Tier projects after 7 consecutive days of inactivity.
   - When paused, Supabase completely removes the project's DNS records, so the server cannot resolve the URL.
   - **Fix**: Log into the [Supabase Dashboard](https://supabase.com/dashboard), click on your project, and click **"Restore project"**. It will resume in ~1-2 minutes.
2. **Incorrect URL Format in Secrets**:
   - Make sure `SUPABASE_URL` in Streamlit Cloud Settings > Secrets starts with `https://` (e.g. `https://your-project.supabase.co`).
   - Ensure there are no trailing slashes or accidental spaces.
3. **Local Fallback Mode**:
   - The app includes an automatic SQLite fallback. Even if Supabase is temporarily paused or unreachable, the chatbot will continue functioning without crashing, allowing appointments to be booked and tested.

**Your app will be live at `https://your-app-name.streamlit.app`!** 🏥🚀
