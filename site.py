from flask import Flask, send_from_directory, render_template, abort
import os

app = Flask(__name__)

#IMAGE_FOLDER = "photo_site/photos"
IMAGE_FOLDER = os.path.join(os.getcwd(), "runtime-images")

@app.route("/")
def index():
    images = [f for f in os.listdir(IMAGE_FOLDER) if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif"))]

    return render_template("site-structure.html", images = images)

# abort is used here in case the path to the file name does not exist
@app.route("/image/<filename>")
def get_images(filename):
    if not os.path.exists(os.path.join(IMAGE_FOLDER, filename)):
        abort(404)
    # if it does exist then return the file from that directory
    return send_from_directory(IMAGE_FOLDER, filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)