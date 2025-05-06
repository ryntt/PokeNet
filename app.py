import json
import sqlite3

import markdown
from os import environ as env
from urllib.parse import quote_plus, urlencode

import openai
from authlib.integrations.base_client import OAuthError
from openai import OpenAI
from authlib.integrations.flask_client import OAuth
from dotenv import find_dotenv, load_dotenv
from flask import Flask, redirect, session, url_for, jsonify, \
    render_template, request, flash

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

tcg_db = sqlite3.connect('tcg_database.db')
tcg_db.execute(
    '''
    CREATE TABLE IF NOT EXISTS cards (
        user_id VARCHAR(255),
        card_name VARCHAR(255),
        card_set VARCHAR(255),
        card_id VARCHAR(30),
        UNIQUE(user_id, card_id)
    )
    '''
)

tcg_db.close()


@app.route('/login')
def login_page():  # put application's code here
    return oauth.auth0.authorize_redirect(
        redirect_uri=url_for("callback", _external=True)
    )


@app.route("/callback", methods=["GET", "POST"])
def callback():
    try:
        token = oauth.auth0.authorize_access_token()
        session["user"] = token
        return redirect("/")
    except OAuthError:
        return redirect("/")

@app.route('/')
def home_page():
    user = session.get('user', {}).get('userinfo', {})
    user_sub = user.get('sub')
    return render_template('home.html', session=session.get('user'),
                           pretty=json.dumps(session.get('user'),
                                             indent=4))


@app.route('/investment', methods=['GET', 'POST'])
def investment_page():
    if 'user' not in session:
        return redirect(url_for('login_page'))
    if request.method == 'POST':
        card_name = request.form['card_name']
        card_set = request.form['set']
        card_rarity = request.form['rarity']
        return redirect(url_for('investment_result', card_name=card_name,
                                card_set=card_set, card_rarity=card_rarity))
    return render_template('investment.html')


@app.route('/investment_result')
def investment_result():
    if 'user' not in session:
        return redirect(url_for('login_page'))
    card_name = request.args.get('card_name').strip()
    card_set = request.args.get('card_set').strip()
    card_rarity = request.args.get('card_rarity').strip()
    try:
        resulting_card = Card.where(q=f'set.name:"{card_set}" '
                                      f'name:"{card_name}" '
                                      f'rarity:"{card_rarity}"')[0]
        resulting_card_img = resulting_card.images.small
        prompt = f"Give me the price trends of a " \
                 f"Pokemon card based on the following information I give you:" \
                 f"card name = {resulting_card.name}, " \
                 f"card set = {resulting_card.set}, " \
                 f"card rarity = {resulting_card.rarity}, " \
                 f"card prices = {resulting_card.tcgplayer.prices}." \
                 f"Then, give me some advice on whether I should invest in this " \
                 f"card or not. Be concise but detailed."
        client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
        completion = client.chat.completions.create(
            model="lmstudio-community/Meta-Llama-3-8B-Instruct-GGUF",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
        )

        msg = markdown.markdown(completion.choices[0].message.content)
        return render_template('investment_result.html', message=msg,
                               img=resulting_card_img)
    except IndexError:
        flash(
            f'Card "{card_name}" from "{card_set}" does not exist.',
            'warning')
        return redirect(url_for('investment_page'))
    except openai.APIConnectionError:
        flash('There was a problem connecting to the server. Please try '
              'again.')
        return redirect(url_for('investment_page'))


@app.route('/search', methods=['GET', 'POST'])
def search_page():
    if 'user' not in session:
        return redirect(url_for('login_page'))
    if request.method == "POST":
        card_name = request.form['name']
        card_set = request.form['set']
        card_rarity = request.form['rarity']
        card_artist = request.form['artist']
        return redirect(url_for('search_result', card_name=card_name,
                                card_set=card_set, card_rarity=card_rarity,
                                card_artist=card_artist))
    return render_template('search.html')


@app.route('/search_result')
def search_result():
    if 'user' not in session:
        return redirect(url_for('login_page'))
    card_name = request.args.get('card_name').strip()
    card_set = request.args.get('card_set').strip()
    card_rarity = request.args.get('card_rarity').strip()
    card_artist = request.args.get('card_artist').strip()
    query_string = ""
    query_string += f'name:"{card_name}" ' if card_name != "" else " "
    query_string += f'set.name:"{card_set}" ' if card_set != "" else " "
    query_string += f'rarity:"{card_rarity}" ' if card_rarity != "" \
        else " "
    query_string += f'artist:"{card_artist}" ' if card_artist != "" \
        else " "
    result = Card.where(q=query_string)
    if not result:
        flash("Card could not be found.")
        return redirect(url_for('search_page'))
    print(f"Query string: {query_string}")
    return render_template('search_result.html', cards=result)


@app.route('/add_cards', methods=['POST'])
def add_cards():
    if 'user' not in session:
        return redirect(url_for('login_page'))
    card_id = request.form.get('card_image_url').strip()
    card_name = request.form.get('card_name').strip()
    card_set = request.form.get('card_set').strip()
    user_id = session.get('user', {}).get('userinfo', {}).get('sub')
    print(user_id)
    conn = sqlite3.connect('tcg_database.db')
    c = conn.cursor()
    try:
        c.execute(
            'INSERT INTO cards (user_id, card_name, card_set, card_id) VALUES (?, ?, ?, ?)',
            (user_id, card_name, card_set, card_id)
        )
        flash(f'Added card: {card_name} ({card_set})', 'success')
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        flash(
            f'Card "{card_name}" from "{card_set}" already exists in your list.',
            'warning')
    return redirect(request.referrer or url_for('search_result'))


@app.route('/list', methods=['GET', 'POST'])
def list_cards():
    if 'user' not in session:
        return redirect(url_for('login_page'))
    user_id = session.get('user', {}).get('userinfo', {}).get('sub')
    conn = sqlite3.connect('tcg_database.db')
    c = conn.cursor()
    if request.method == 'POST':
        deleted_card = request.form.get('card_image_url').strip()
        if deleted_card:
            # Delete the card from the database
            c.execute('DELETE FROM cards WHERE user_id = ? AND card_id = ?',
                      (user_id, deleted_card))
            conn.commit()
    c.execute(
        'SELECT card_name, card_set, card_id FROM cards WHERE user_id = ?',
        (user_id,)
    )
    rows = c.fetchall()
    conn.close()

    cards = [
        {'name': row[0], 'set': {'name': row[1]}, 'images': {'small': row[2]}}
        for row in rows
    ]
    conn.close()
    return render_template('list.html', cards=cards)


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
    app.run(host="0.0.0.0", port=80)
