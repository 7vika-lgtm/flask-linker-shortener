# Shortly: a link shortener with click analytics (Flask)

**Skill:** Flask, Jinja2, SQLite, form handling and validation.

## Features
- Create short links with random or custom aliases
- Input validation and flash messages
- Click tracking and a per-link stats page (clicks per day)
- Delete links, dark-mode friendly UI

## Run
Save `1-flask_app.py` as `app.py`, then:
```bash
pip install Flask
python app.py        # http://127.0.0.1:5000
```
Everything (routes, database code and HTML templates) is in that single file.

## Ideas to extend
User accounts (Flask-Login), QR codes, link expiry, rate limiting, deploy on Render or PythonAnywhere.
