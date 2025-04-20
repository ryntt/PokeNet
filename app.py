import json
import markdown
from os import environ as env
from urllib.parse import quote_plus, urlencode
from openai import OpenAI
from authlib.integrations.flask_client import OAuth
from dotenv import find_dotenv, load_dotenv
from flask import Flask, redirect, session, url_for, jsonify, render_template

from pokemontcgsdk import Card, Set, Type, Supertype, Subtype, Rarity

ENV_FILE = find_dotenv()
if ENV_FILE:
    load_dotenv(ENV_FILE)

app = Flask(__name__)
app.secret_key = env.get("APP_SECRET_KEY")

oauth = OAuth(app)

oauth.register(
    "auth0",
    client_id=env.get("AUTH0_CLIENT_ID"),
    client_secret=env.get("AUTH0_CLIENT_SECRET"),
    client_kwargs={
        "scope": "openid profile email",
    },
    server_metadata_url=f'https://{env.get("AUTH0_DOMAIN")}/.well-known/openid-configuration'
)


@app.route('/login')
def login_page():  # put application's code here
    return oauth.auth0.authorize_redirect(
        redirect_uri=url_for("callback", _external=True)
    )


@app.route("/callback", methods=["GET", "POST"])
def callback():
    token = oauth.auth0.authorize_access_token()
    session["user"] = token
    return redirect("/")


@app.route('/')
def home_page():
    return render_template('home.html', session=session.get('user'),
                           pretty=json.dumps(session.get('user'), indent=4))


@app.route('/investment')
def investment_page():
    return render_template('investment.html')


@app.route('/investment_result')
def investment_result():
    client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
    completion = client.chat.completions.create(
        model="lmstudio-community/Meta-Llama-3-8B-Instruct-GGUF",
        messages=[
            {"role": "user", "content": "say hello"}
        ],
        temperature=0.7,
    )

    msg = markdown.markdown(completion.choices[0].message.content)
    return render_template('investment_result.html', message=msg)


@app.route('/search')
def search_page():
    return render_template('search.html')


@app.route('/list')
def list_page():
    return render_template('list.html')


@app.route("/logout")
def logout():
    session.clear()
    return redirect(
        "https://" + env.get("AUTH0_DOMAIN")
        + "/v2/logout?"
        + urlencode(
            {
                "returnTo": url_for("home_page", _external=True),
                "client_id": env.get("AUTH0_CLIENT_ID"),
            },
            quote_via=quote_plus,
        )
    )


if __name__ == '__main__':
    app.run()
