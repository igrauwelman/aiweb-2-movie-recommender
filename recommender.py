# Contains parts from: https://flask-user.readthedocs.io/en/latest/quickstart_app.html
import os

from flask import Flask, render_template, request
from flask_user import login_required, UserManager, current_user

from get_data import get_user_preferences_from_database, get_movies_on_watchlist, get_ignored_movies, \
    get_genre_and_decade_filtered_recommendations
from models import db, User, MovieRating
from preparation import preprocess_tags, get_and_save_amount_of_ratings_and_average_ratings, \
    initialize_user_movie_scores
from read_data import check_and_read_data
from recommendation import (get_movie_recommendations, add_movie_to_watchlist, delete_movie_from_watchlist,
                            save_survey_preferences_and_check_for_recalculation, get_all_movies_and_users_ids,
                            update_data_after_rating, get_all_rated_movies_by_current_user, add_new_rating_or_update,
                            ignore_movie_for_recommendations, revoke_ignore_movie_for_recommendations,
                            get_survey_preferences, update_scores_of_ignored_or_rated_movie)
from searcher import find_movies_by_query

global score_recalculation_needed_for, all_movie_ids, all_user_ids


# Class-based application configuration
class ConfigClass(object):
    """ Flask application config """

    # Flask settings
    SECRET_KEY = os.urandom(32).hex()

    # Flask-SQLAlchemy settings
    SQLALCHEMY_DATABASE_URI = 'sqlite:///movie_recommender.sqlite'  # File-based SQL database
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # Avoids SQLAlchemy warning

    # Flask-User settings
    USER_APP_NAME = "MovieRex"  # Shown in and email templates and page footers
    USER_ENABLE_EMAIL = False  # Disable email authentication
    USER_ENABLE_USERNAME = True  # Enable username authentication
    USER_REQUIRE_RETYPE_PASSWORD = True  # Simplify register form

    USER_AFTER_REGISTER_ENDPOINT = 'welcome_survey'
    USER_AFTER_CONFIRM_ENDPOINT = 'welcome_survey'
    USER_AFTER_LOGIN_ENDPOINT = 'home_page'
    USER_AFTER_LOGOUT_ENDPOINT = 'home_page'
    USER_AFTER_CHANGE_PASSWORD_ENDPOINT = 'home_page'
    USER_AFTER_CHANGE_USERNAME_ENDPOINT = 'home_page'


# Create Flask app
app = Flask(__name__)
app.config.from_object(__name__ + '.ConfigClass')  # configuration
app.app_context().push()  # create an app context before initializing db
db.init_app(app)  # initialize database
db.create_all()  # create database if necessary
user_manager = UserManager(app, db, User)  # initialize Flask-User management
all_movie_ids, all_user_ids = get_all_movies_and_users_ids()
score_recalculation_needed_for = ()


# needed in case more than one user is logged in via VPN on the server
@app.after_request
def add_header(response):
    response.cache_control.private = True
    response.cache_control.public = False
    return response


# @app.cli.command('initdb')
def initdb_command():
    global db
    """Creates the database tables."""
    check_and_read_data(db, testing=False)
    preprocess_tags()
    get_and_save_amount_of_ratings_and_average_ratings()
    # print('Initialized the database.')


# The home page has two templates depending on whether the user is authenticated
@app.route('/')
def home_page():
    global all_movie_ids, score_recalculation_needed_for
    # show homepage with a few movies/recommendations if user is already signed in
    if current_user.is_authenticated:
        user = User.query.filter(User.id == current_user.id).first()
        # initialize movie scores in database if not done for the user already
        if not user.initialized_scores:
            # print("initialize movie scores")
            initialize_user_movie_scores()
            # print("done with initializing movie scores")
            setattr(user, 'initialized_scores', True)
            movies = get_movie_recommendations(4, 4.0, 48, "hybrid")
            score_recalculation_needed_for = ()
        else:
            movies = get_movie_recommendations(4, 4.0, 48, "hybrid",
                                               calculation_needed_for=score_recalculation_needed_for)
            if score_recalculation_needed_for:
                score_recalculation_needed_for = ()
        movies_watchlist = get_movies_on_watchlist()
        return render_template("home.html", movies=movies, movies_watchlist=movies_watchlist)
    else:  # show homepage with options to register or sign in if user has not done so
        return render_template("home01.html")


@app.route('/rate', methods=['GET', 'POST'])
@login_required
def rate():
    global score_recalculation_needed_for
    rating = request.form.get('rating')
    movie_id = request.form.get('movieID')
    # print("Rating", rating, "for movie id: ", movie_id)
    score_recalculation_needed_for = tuple(set(score_recalculation_needed_for + ('user-based', 'item-based',
                                                                                 'explorative', 'hybrid')))
    add_new_rating_or_update(movie_id, rating)
    update_data_after_rating(int(movie_id), float(rating))
    return render_template("rated.html", rating=rating)


@app.route('/ignore', methods=['GET', 'POST'])
@login_required
def ignore():
    global score_recalculation_needed_for
    movie_id = request.form.get('movieID')
    # print("Ignore movie:", movie_id)
    ignore_movie_for_recommendations(int(movie_id))
    # if the movie was rated, score recalculation is needed
    rating_entry = MovieRating.query.filter(
        MovieRating.movie_id == movie_id,
        MovieRating.user_id == current_user.id
        ).first()
    if rating_entry.rating is not None:
        score_recalculation_needed_for = tuple(set(score_recalculation_needed_for + ('user-based', 'item-based',
                                                                                     'explorative', 'hybrid')))
    # else no recalculation is needed, but setting the movie scores to 0 necessary to exclude movie from recommendations
    else:
        update_scores_of_ignored_or_rated_movie(int(movie_id))
    # return home page (although the return value is technically not used)
    return render_template("home.html")


@app.route('/revoke_ignore', methods=['GET', 'POST'])
@login_required
def revoke_ignore():
    global score_recalculation_needed_for
    movie_id = request.form.get('movieID')
    # print("Revoke ignore for movie:", movie_id)
    revoke_ignore_movie_for_recommendations(int(movie_id))
    # score recalculation is needed (if the movie was rated, revoke the consequences of ignoring the movie, if it was
    # not rated yet, recalculate the scores to include the movie again)
    score_recalculation_needed_for = tuple(set(score_recalculation_needed_for + ('user-based', 'item-based',
                                                                                 'explorative', 'hybrid')))
    # return home page (although the return value is technically not used)
    return render_template("home.html")


@app.route('/welcome_survey')
@login_required
def welcome_survey():
    return render_template("survey.html", is_erroneous=False, is_new=True)


@app.route('/survey')
@login_required
def survey_page():
    liked_genres_survey, disliked_genres_survey = get_survey_preferences()
    return render_template("survey.html", is_erroneous=False, liked_genres_survey=liked_genres_survey,
                           disliked_genres_survey=disliked_genres_survey)


@app.route('/survey_submit', methods=['GET', 'POST'])
@login_required
def survey_submit():
    global score_recalculation_needed_for
    incl_genres = request.form.getlist('genre-incl')
    # print("survey response liked genres:", incl_genres)
    excl_genres = request.form.getlist('genre-excl')
    # print("survey response disliked genres:", excl_genres)
    score_recalculation_needed_for = tuple(set(score_recalculation_needed_for +
                                               save_survey_preferences_and_check_for_recalculation(incl_genres,
                                                                                                   excl_genres)))
    # refresh loads home page directly after feedback
    return render_template('survey_submit.html'), {"Refresh": "1; url=../recommender.wsgi/"}


@app.route('/loading')
@login_required
def loading():
    # refresh to home page
    return render_template('loading.html'), {"Refresh": "1; url=../recommender.wsgi/"}


@app.route('/rated_movies')
@login_required
def rated_movies_page():
    rated_movies, ratings = get_all_rated_movies_by_current_user()
    ignored_movies = get_ignored_movies()
    ignored_movies_ids = [m.id for m in ignored_movies]
    if len(rated_movies) == 0:
        no_movies = True
    else:
        no_movies = False
    return render_template("rated_movies.html", rated_movies=rated_movies, ratings=ratings,
                           ignored_movies=ignored_movies, ignored_movies_ids=ignored_movies_ids, no_movies=no_movies)


@app.route('/ignored_movies')
@login_required
def ignored_movies_page():
    rated_movies, ratings = get_all_rated_movies_by_current_user()
    movies_watchlist = get_movies_on_watchlist()
    ignored_movies = get_ignored_movies()
    ignored_movies_ids = [m.id for m in ignored_movies]
    if len(ignored_movies) == 0:
        no_movies = True
    else:
        no_movies = False
    return render_template("ignored_movies.html", rated_movies=rated_movies, ratings=ratings,
                           ignored_movies=ignored_movies, movies_watchlist=movies_watchlist,
                           ignored_movies_ids=ignored_movies_ids, no_movies=no_movies)


@app.route('/search')
@login_required
def search():
    movie_terms = request.args.get('movie_terms')
    movies_results_titles, movies_results_tags = find_movies_by_query(movie_terms, 81)
    # print("Title-based: ", [(m.id, m.title) for m in movies_results_titles])
    # print("Tag-based: ", [(m.id, m.title) for m in movies_results_tags])
    ignored_movies = get_ignored_movies()
    ignored_movies_ids = [m.id for m in ignored_movies]
    movies_watchlist = get_movies_on_watchlist()
    if not movies_results_titles and not movies_results_tags:
        no_results = True
    else:
        no_results = False
    rated_movies, ratings = get_all_rated_movies_by_current_user()
    results_titles_num = len(movies_results_titles)
    results_tags_num = len(movies_results_tags)
    return render_template("search_results.html", movie_terms=movie_terms,
                           movies_results_titles=movies_results_titles,
                           movies_results_tags=movies_results_tags, movies_watchlist=movies_watchlist,
                           no_results=no_results, results_titles_num=results_titles_num,
                           results_tags_num=results_tags_num, rated_movies=rated_movies, ratings=ratings,
                           ignored_movies=ignored_movies, ignored_movies_ids=ignored_movies_ids)


@app.route('/watchlist')
@login_required
def watchlist_page():
    watchlist_movies = get_movies_on_watchlist()
    rated_movies, ratings = get_all_rated_movies_by_current_user()
    ignored_movies = get_ignored_movies()
    ignored_movies_ids = [m.id for m in ignored_movies]
    if len(watchlist_movies) == 0:
        no_movies = True
    else:
        no_movies = False
    return render_template("watchlist.html", watchlist_movies=watchlist_movies,
                           rated_movies=rated_movies, ratings=ratings, ignored_movies=ignored_movies,
                           ignored_movies_ids=ignored_movies_ids, no_movies=no_movies)


@app.route('/add_watchlist', methods=['GET', 'POST'])
@login_required
def add_watchlist():
    movie_id = request.form.get('movieID')
    add_movie_to_watchlist(int(movie_id))
    return render_template("added.html")


@app.route('/remove_watchlist', methods=['GET', 'POST'])
@login_required
def remove_watchlist():
    movie_id = request.form.get('movieID')
    delete_movie_from_watchlist(movie_id)
    rated_movies, ratings = get_all_rated_movies_by_current_user()
    return render_template("removed.html", rated_movies=rated_movies, ratings=ratings)


@app.route('/preferences')
@login_required
def preferences_page():
    # lists with genres and decades; min_ratio: minimum of 60% need to be liked (= min. 4.0 rating)
    extracted_liked_genres, extracted_disliked_genres, extracted_liked_decades, extracted_disliked_decades = (
        get_user_preferences_from_database(min_ratio=0.7))
    liked_genres = False
    disliked_genres = False
    liked_decades = False
    disliked_decades = False
    liked_genres_sur = False
    disliked_genres_sur = False
    if len(extracted_liked_genres) > 0:
        liked_genres = True
    if len(extracted_disliked_genres) > 0:
        disliked_genres = True
    if len(extracted_liked_decades) > 0:
        liked_decades = True
    if len(extracted_disliked_decades) > 0:
        disliked_decades = True
    liked_genres_survey, disliked_genres_survey = get_survey_preferences()
    if len(liked_genres_survey) > 0:
        liked_genres_sur = True
    if len(disliked_genres_survey) > 0:
        disliked_genres_sur = True
    return render_template('preferences.html', extracted_liked_genres=extracted_liked_genres,
                           extracted_disliked_genres=extracted_disliked_genres,
                           extracted_liked_decades=extracted_liked_decades,
                           extracted_disliked_decades=extracted_disliked_decades, liked_genres=liked_genres,
                           disliked_genres=disliked_genres, liked_decades=liked_decades,
                           disliked_decades=disliked_decades, liked_genres_survey=liked_genres_survey,
                           disliked_genres_survey=disliked_genres_survey, liked_genres_sur=liked_genres_sur,
                           disliked_genres_sur=disliked_genres_sur)


@app.route('/filter')
@login_required
def filter():
    movies_watchlist = get_movies_on_watchlist()
    genre_filter = request.args.get('genre')
    decade_filter = request.args.get('decade')
    results = get_genre_and_decade_filtered_recommendations(genre_filter, decade_filter, 48)
    rated_movies, ratings = get_all_rated_movies_by_current_user()
    if len(results) == 0:
        no_results = True
    else:
        no_results = False
        # ignored movies are technically not shown here, but just in case:
    ignored_movies = get_ignored_movies()
    ignored_movies_ids = [m.id for m in ignored_movies]
    return render_template("filter.html", results=results, no_results=no_results,
                           genre_filter=genre_filter, decade_filter=decade_filter, movies_watchlist=movies_watchlist,
                           rated_movies=rated_movies, ratings=ratings, ignored_movies=ignored_movies,
                           ignored_movies_ids=ignored_movies_ids)


# Start development web server
if __name__ == '__main__':
    initdb_command()
    app.run(port=5000, debug=True)
