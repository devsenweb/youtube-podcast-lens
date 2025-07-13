# YouTube Podcast Lens

A web application that lets you analyze YouTube videos as podcasts: fetch transcripts, segment topics, and visualize content.  
**Now with Google Login!**

---

## Features

- **Google OAuth Login:** Secure authentication using your Google account.
- **Transcript Fetching:** Enter a YouTube URL or video ID to fetch and analyze the transcript.
- **Topic Segmentation:** Automatic segmentation of video content into topics.
- **User Dashboard:** Displays your Google profile info when logged in.
- **Session Management:** Secure session handling with FastAPI.
- **Plain HTML/JS Frontend:** No frontend frameworks—simple, fast, and easy to customize.

---

## Tech Stack

- **Backend:** FastAPI (Python)
- **Frontend:** Plain HTML, JavaScript, TailwindCSS (via CDN)
- **OAuth:** Google OAuth 2.0 via Authlib
- **Session Management:** Starlette SessionMiddleware
- **Async HTTP:** httpx
- **Environment Variables:** python-dotenv

---

## Getting Started

### 1. Clone the Repository

```sh
git clone https://github.com/yourusername/youtube-podcast-lens.git
cd youtube-podcast-lens/backend
```

### 2. Install Dependencies

It’s recommended to use a virtual environment:

```sh
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Set Up Google OAuth Credentials

- Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
- Create an OAuth 2.0 Client ID (type: Web application).
- Set the **Authorized redirect URI** to:  
  `http://localhost:8000/auth/google/callback`
- Download your credentials or copy:
  - `GOOGLE_CLIENT_ID`
  - `GOOGLE_CLIENT_SECRET`

### 4. Configure Environment Variables

Create a `.env` file in the `backend` directory:

```env
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
SECRET_KEY=your-random-secret-key
```

### 5. Run the Server

```sh
uvicorn main:app --reload
```

The app will be available at [http://localhost:8000](http://localhost:8000).

---

## Usage

1. Open [http://localhost:8000](http://localhost:8000) in your browser.
2. Click **Login with Google** and authenticate.
3. Enter a YouTube URL or Video ID and click **Fetch Transcript**.
4. View transcript, topic segments, and your Google profile info.

---

## Project Structure

```
youtube-podcast-lens/
  backend/
    main.py           # FastAPI backend (OAuth, API, session, static files)
    db.py             # (If present) Database logic
    requirements.txt  # Python dependencies
    .env              # Environment variables (not committed)
    static/
      index.html      # Frontend HTML
      main.js         # Frontend JS
      style.css       # (Optional) Custom styles
```

---

## Security Notes

- Never commit your `.env` file or secrets to version control.
- For production, set up HTTPS and use a strong, random `SECRET_KEY`.
- Tailwind is loaded via CDN for development; for production, use the [recommended installation](https://tailwindcss.com/docs/installation).

---

## Troubleshooting

- **Login button not hiding?**  
  Make sure your browser loads `/static/main.js` and that you are not using a cached version. Hard refresh (`Ctrl+F5`).
- **OAuth errors?**  
  Double-check your Google credentials and redirect URI in the Cloud Console and `.env`.
- **Backend errors?**  
  Check the terminal for Python exceptions and ensure all dependencies are installed.

---

## License

MIT License