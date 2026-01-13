from flask import Flask, send_from_directory, render_template
import os

app = Flask(__name__)

#IMAGE_FOLDER = "photo_site/photos"
IMAGE_FOLDER = "static"

@app.route("/")
def index():
    files = os.path.join(app.static_folder, "images")
    print("Image directory:", files)
    print("Files found:", os.listdir(files))
    image_files = [f for f in os.listdir(files) if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif"))]

    return render_template("site-structure.html", images = image_files)

@app.route("/image/<filename>")
def image(filename):
    return send_from_directory(IMAGE_FOLDER, filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
