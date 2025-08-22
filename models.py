from flask_sqlalchemy import SQLAlchemy
from flask_user import UserMixin

db = SQLAlchemy()


# Define the User data-model.
# NB: Make sure to add flask_user UserMixin as this adds additional fields and properties required by Flask-User
class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    active = db.Column('is_active', db.Boolean(), nullable=False, server_default='1')
    initialized_scores = db.Column(db.Boolean(), nullable=False, server_default='0')

    # User authentication information. The collation='NOCASE' is required
    # to search case insensitively when USER_IFIND_MODE is 'nocase_collation'.
    username = db.Column(db.String(100, collation='NOCASE'), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False, server_default='')
    email_confirmed_at = db.Column(db.DateTime())

    # User information
    first_name = db.Column(db.String(100, collation='NOCASE'), nullable=False, server_default='')
    last_name = db.Column(db.String(100, collation='NOCASE'), nullable=False, server_default='')

    genre_preferences = db.relationship('UserGenrePreferences', backref='user', lazy=True)
    decade_preferences = db.relationship('UserDecadePreferences', backref='user', lazy=True)
    ratings = db.relationship('MovieRating', backref='user', lazy=True)
    tags = db.relationship('Tags', backref='user', lazy=True)
    watchlist = db.relationship('MovieWatchList', backref='user', lazy=True)
    movie_score = db.relationship('UserMovieRecommendationScores', backref='user', lazy=True)


class UserGenrePreferences(db.Model):
    __tablename__ = 'user_genre_preferences'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    genre = db.Column(db.String(255), nullable=False, server_default='')
    survey_response = db.Column(db.Integer)  # 0 = exclude, 1 = include
    amount_of_ratings = db.Column(db.Integer)
    amount_of_likes = db.Column(db.Integer)
    amount_of_dislikes = db.Column(db.Integer)


class UserDecadePreferences(db.Model):
    __tablename__ = 'user_decade_preferences'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    decade = db.Column(db.Integer)
    amount_of_ratings = db.Column(db.Integer)
    amount_of_likes = db.Column(db.Integer)
    amount_of_dislikes = db.Column(db.Integer)


class UserMovieRecommendationScores(db.Model):
    __tablename__ = 'user_movie_scores'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    movie_id = db.Column(db.Integer, db.ForeignKey('movies.id'), nullable=False)
    survey_based_score = db.Column(db.Float, nullable=False, server_default='')
    user_based_score = db.Column(db.Float, nullable=False, server_default='')
    item_based_score = db.Column(db.Float, nullable=False, server_default='')
    exploration_based_score = db.Column(db.Float, nullable=False, server_default='')
    total_recommendation_score = db.Column(db.Float, nullable=False, server_default='')


class Movie(db.Model):
    __tablename__ = 'movies'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100, collation='NOCASE'), nullable=False, unique=True)
    release_year = db.Column(db.Integer, nullable=True)
    amount_of_ratings = db.Column(db.Integer, nullable=True)
    average_rating = db.Column(db.Float, nullable=True)
    genres = db.relationship('MovieGenre', backref='movie', lazy=True)
    ratings = db.relationship('MovieRating', backref='movie', lazy=True)
    links = db.relationship('Links', backref='movie', lazy=True)
    tags = db.relationship('Tags', backref='movie', lazy=True)
    watchlist = db.relationship('MovieWatchList', backref='movie', lazy=True)
    movie_score = db.relationship('UserMovieRecommendationScores', backref='movie', lazy=True)


class MovieGenre(db.Model):
    __tablename__ = 'movie_genres'
    id = db.Column(db.Integer, primary_key=True)
    movie_id = db.Column(db.Integer, db.ForeignKey('movies.id'), nullable=False)
    genre = db.Column(db.String(255), nullable=True, server_default='')


class MovieRating(db.Model):
    __tablename__ = 'movie_ratings'
    id = db.Column(db.Integer, primary_key=True)
    movie_id = db.Column(db.Integer, db.ForeignKey('movies.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating = db.Column(db.Float, nullable=True, server_default='')
    time_rated = db.Column(db.Integer)
    ignored = db.Column(db.Boolean)
    time_ignored = db.Column(db.Integer)


class MovieWatchList(db.Model):
    __tablename__ = 'movie_watchlist'
    id = db.Column(db.Integer, primary_key=True)
    movie_id = db.Column(db.Integer, db.ForeignKey('movies.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    time_added = db.Column(db.Integer)
    rated = db.Column(db.Boolean)
    ignored = db.Column(db.Boolean)


class Links(db.Model):
    __tablename__ = 'links'
    id = db.Column(db.Integer, primary_key=True)
    movie_id = db.Column(db.Integer, db.ForeignKey('movies.id'), nullable=False)
    imdb_id = db.Column(db.Integer)
    tmdb_id = db.Column(db.Integer)


class Tags(db.Model):
    __tablename__ = 'tags'
    __table_args__ = (db.UniqueConstraint("movie_id", "tag"),)
    id = db.Column(db.Integer, primary_key=True)
    movie_id = db.Column(db.Integer, db.ForeignKey('movies.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tag = db.Column(db.String(255), nullable=False, server_default='')
    timestamp = db.Column(db.Integer)
