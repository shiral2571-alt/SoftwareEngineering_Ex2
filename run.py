"""Start the teaching tool:  py run.py   (then open http://localhost:5000/lecturer)"""
import os

from app import create_app

app = create_app(os.environ.get("DB_PATH", "teaching_tool.db"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  Lecturer dashboard: http://localhost:{port}/lecturer")
    print(f"  Lecturer PIN:       {app.config['LECTURER_PIN']}")
    print(f"  AI engine:          {app.extensions['services']['llm'].name}")
    print(f"  Phones need HTTPS:  cloudflared tunnel --url http://localhost:{port}\n")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
