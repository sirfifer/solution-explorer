"""Service that reads and writes entities (drives entity_access)."""
from app.models.sqlalchemy_models import User


def create_user(session, email, name):
    user = User(email=email, name=name)
    session.add(user)
    session.commit()
    return user


def find_user(session, user_id):
    return session.query(User).filter(User.id == user_id).first()


def raw_articles(conn):
    # A string-matched table reference (inferred access).
    return conn.execute("SELECT * FROM articles")
