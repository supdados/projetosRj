import os

from app import app

application = app

if __name__ == "__main__":
    application.run(
        debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true',
        host='0.0.0.0',
        port=5002,
    )
