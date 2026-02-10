from flask import Flask, send_from_directory, render_template, abort, request, redirect, url_for, session
import google_auth_oauthlib.flow
import json
import os
import requests
from googleapiclient.discovery import build
import googleapiclient.errors
import google.oauth2.credentials


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
        return "Access Denied: Your account is not authorized.", 403

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

@app.route('/login', methods=['POST'])
def login():
    uname = request.form['uname']
    passwd = request.form['passwd']
    # put logic here
    if uname == "Obi-wan" and passwd == "12345":
        return redirect(url_for('dashboard'))
    return "Login failed", 400

# @app.route('/login-page')
# def dashboard():
#     return render_template('login-page.html')

@app.route('/')
def welcome():
    if "access_token" in session:
        user_info = get_user_info(session["access_token"])
        if user_info:
            return f"""
            Hello {user_info["given_name"]}!<br>
            Your email address is {user_info["email"]}<br>
            <a href="/signin">Sign In to Google</a><br>
            """
    return """
    <h1>Welcome to Google Sheet Importer</h1>
    <a href="/signin">Sign In to Google</a><br>
    """


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)