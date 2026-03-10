from flask import Flask, send_from_directory, render_template, abort, request, redirect, url_for, session
import google_auth_oauthlib.flow
import json
import os
import requests
from googleapiclient.discovery import build
import googleapiclient.errors
import google.oauth2.credentials
import cv2
import numpy as nb

# make sure to run the command `lt --port 5000 --subdomain software-defined-radio-transmission`
# then access the app through the url provided so the google authentication works

app = Flask(__name__)

# code to use google authentication adapted from: https://docs.replit.com/additional-resources/google-auth-in-flask#google-sheets-api-setup

# `FLASK_SECRET_KEY` is used by sessions
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or os.urandom(24)

ALLOWED_EMAIL = "obiwan.kenobi33774442@gmail.com"

# `GOOGLE_APIS_OAUTH_SECRET` contains the contents of a JSON file to be downloaded
# from the Google Cloud Credentials panel
import json

with open('client_secret.json', 'r') as f:
    google_oauth_secrets = json.load(f)
    
# oauth_config = json.loads(os.environ['GOOGLE_OAUTH_SECRETS'])

# environment variable to allow for insecure transport (aka, http instead of https)
# since https isn't working with firefox
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'


scopes = [
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid"
]
# This sets up a configuration for the OAuth flow
oauth_flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
    'client_secret.json',
    # scopes define what APIs you want to access on behave of the user once authenticated
    scopes=scopes
)

oauth_flow.redirect_uri = 'http://localhost:5000/oauth2callback'

# This is entrypoint of the login page. It will redirect to the Google login service located at the `authorization_url`. 
# The `redirect_uri` is actually the URI which the Google login service will use to redirect back to this app.
@app.route('/signin')
def signin():

    oauth_flow.redirect_uri = url_for('oauth2callback', _external=True)
    # .replace('http://', 'https://')
    authorization_url, state = oauth_flow.authorization_url(prompt='select_account')
    session['state'] = state
    return redirect(authorization_url)

# This is the endpoint that Google login service redirects back to. It must be added to the "Authorized redirect URIs"
# in the API credentials panel within Google Cloud. It will call a Google endpoint to request
# an access token and store it in the user session. After this, the access token can be used to access APIs on behalf of the user
@app.route('/oauth2callback')
def oauth2callback():
    if not session['state'] == request.args['state']:
        return 'Invalid state parameter', 400
    oauth_flow.fetch_token(authorization_response=request.url)
                        #    .replace('http:', 'https:'))
    # get the credentials of the user trying to login
    credentials = oauth_flow.credentials
    session['access_token'] = credentials.token
    # return redirect(url_for('dashboard'))
        
    # code to try to look for a specific google user, doesn't work 
    user_info_response = requests.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        params={'access_token': oauth_flow.credentials.token}
    )
    
    if not user_info_response.ok:
        print(f"Error from Google: {user_info_response.text}")
        return "Failed to get user info", 400

    user_info = user_info_response.json()
    user_email = user_info.get('email')
    
    # if the user email is equal to the hard coded email
    # (since only obi-wan can login)
    if user_email == ALLOWED_EMAIL:
        session['access_token'] = credentials.token
        session['user_email'] = user_email
        return redirect(url_for('dashboard'))
    else:
        # if it is any other account that is not obi-wan's, throw the 403 error code and don't let them see the login page
        session.clear()
        # return "Access Denied: Your account is not authorized.", 403
        return render_template('login-fail.html')

@app.route('/dashboard')
def dashboard():
    if 'access_token' not in session:
        # redirect back to home if not logged in
        return redirect(url_for('index'))
    return render_template('login-page.html')

# Call the userinfo API to get the user's information with a valid access token
def get_user_info(access_token):
    response = requests.get("https://www.googleapis.com/oauth2/v3/userinfo", headers={
       "Authorization": f"Bearer {access_token}"
   })
    if response.status_code == 200:
        user_info = response.json()
        return user_info
    else:
        print(f"Failed to fetch user info: {response.status_code} {response.text}")
        return None

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# decrypts images based on the image path and decryption key
# encryption used through openCV
def decrypt_image(image_path, output_folder, key):
    try:
        
        # Ensure the output directory exists
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            
        # read the image file as raw bytes
        with open(image_path, 'rb') as fin:
            image_data = fin.read()

        # convert image data into a byte array to perform operations
        image_byte_array = bytearray(image_data)

        # perform xor operation on each byte of the image (based on the encryption key)
        for index, value in enumerate(image_byte_array):
            image_byte_array[index] = value ^ key
            
        # Create the full path using the passed folder
        file_name = 'decrypted_' + os.path.basename(image_path)
        decrypted_path = os.path.join(output_folder, file_name)
        
        with open(decrypted_path, 'wb') as fout:
            fout.write(image_byte_array)

        # output_dir = os.path.expanduser('~/runtime-images')
        
        # # making the directory if it does not exist
        # if not os.path.exists(output_dir):
        #     os.makedirs(output_dir)
            
        # # change the name of the file to include 'decrypted_'
        # file_name = 'decrypted_' + os.path.basename(image_path)
        # decrypted_path = os.path.join(output_dir, file_name)

        # # then write the info to the file
        # with open(decrypted_path, 'wb') as fout:
        #     fout.write(image_byte_array)
        
        # # put the decrypted file into the runtime images that the app will pull from
        # decrypted_path = '~/runtime-images/decrypted_' + image_path.split('/')[-1]
        # with open(decrypted_path, 'wb') as fin:
        #     fin.write(image_byte_array)
        
    except Exception as e:
        print(f"Error caught while decrypting: {e}")


#IMAGE_FOLDER = "photo_site/photos"
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
ENCRYPTED_IMAGE_FOLDER = os.path.join(BASE_DIR, "output/encrypted")
IMAGE_FOLDER = os.path.join(BASE_DIR, "runtime-images")

@app.route("/")
def index():
    
    # checks that the encrypted image folder exists
    if not os.path.exists(ENCRYPTED_IMAGE_FOLDER):
        return f"Error: Folder {ENCRYPTED_IMAGE_FOLDER} not found."
    
    encrypted_images = [f for f in os.listdir(ENCRYPTED_IMAGE_FOLDER) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
    for img in encrypted_images:
        # TODO: make sure the path for img is correct, or if it needs to be the path rather than than the actual file
        # the encryption key on the raspberry pi is hard coded here so the server can decrypt
        # this should theoretically put the decrypted images into the runtime-images folder
        img_path = os.path.join(ENCRYPTED_IMAGE_FOLDER, img)
        decrypt_image(img_path, IMAGE_FOLDER, 123)
    
    # then get the images from the runtime-images folder after all the images have been decrypted and populated in this directory
    images = [f for f in os.listdir(IMAGE_FOLDER) 
              if f.lower().endswith((".png", ".jpg", ".jpeg"))]

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