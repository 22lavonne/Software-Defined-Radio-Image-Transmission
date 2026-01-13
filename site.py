from flask import Flask, send_from_directory
import os

app = Flask(__name__)

IMAGE_FOLDER = "photo_site/photos"

@app.route("/")
def index():
    files = os.listdir(IMAGE_FOLDER)
    images = [f for f in files if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif"))]

    html = "<h1>Quick and Dirty</h1>"
    for img in images:
        html += f'<img src="/image/{img}" style="max-width:400px;margin:10px;">'

    return html

@app.route("/image/<filename>")
def image(filename):
    return send_from_directory(IMAGE_FOLDER, filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
