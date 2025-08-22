from flask_login import current_user
from sqlalchemy import case
import math

from models import MovieRating, UserMovieRecommendationScores, Movie, MovieGenre, UserGenrePreferences, db, \
	MovieWatchList, UserDecadePreferences, User

global all_movie_ids, all_user_ids, all_movie_ids_rated


def get_all_movies_and_users_ids():
	"""
	Gets the ids of all movies and all users.

	:return: all_movie_ids - list of the ids of all movies,
			all_user_ids - list of the ids of all users
	"""

	# print("get all movies and users ids")
	global all_movie_ids, all_user_ids

	# get the ids of all movies
	all_movie_ids = db.session.query(Movie.id.distinct()).order_by(Movie.id).all()
	all_movie_ids = [m[0] for m in all_movie_ids]

	# get the ids of all users
	all_user_ids = db.session.query(User.id.distinct()).order_by(User.id).all()
	all_user_ids = [u[0] for u in all_user_ids]
	# print("done (all movie and user ids)")

	return all_movie_ids, all_user_ids


def get_all_rated_movies_ids():
	"""
	Gets all movies that there are ratings of in MovieRating.
	:return: all_movie_ids_rated - list of ids of all movies that were rated at least once
	"""

	global all_movie_ids_rated
	# get all movie ids of the movies there are ratings of
	all_movie_ids_rated = db.session.query(MovieRating.movie_id.distinct()).order_by(MovieRating.movie_id).all()
	all_movie_ids_rated = [m[0] for m in all_movie_ids_rated]

	return all_movie_ids_rated


def get_all_movie_genres():
	"""
	Gets all movie genres in the database.

	:return: genres - list of all genres
	"""

	# print("get all movie genres")
	# get all distinct genres in MovieGenre
	genres = db.session.query(MovieGenre.genre.distinct()).order_by(MovieGenre.genre).all()
	genres = [g[0] for g in genres if g[0] is not None]
	# print("done (all genres)")

	return genres


def get_most_popular_movies(amount_of_results: int, consider_ratings: bool = True):
	"""
	Gets the most popular movies based on the amount of ratings of the movies. If consider_ratings is True, the average
	movie ratings are considered as well.

	:param amount_of_results: amount of results that should be returned
	:param consider_ratings: determines whether the average movie ratings should be included
	:return: most_rated_movies if consider ratings is False - list of Movie objects of the most rated movies,
			most_rated_popular_movies if consider ratings is True - list of Movie objects of the most rated movies with
			an average rating of at least 4.0
	"""

	# get a list of the ids of all movies the current user rated, excluding those they ignored
	movies_already_rated = MovieRating.query.filter(MovieRating.user_id == current_user.id,
	                                                MovieRating.ignored == 0).all()
	movies_already_rated_ids = [m.movie_id for m in movies_already_rated]
	# print("get most rated movies")
	most_rated_movies = db.session.query(Movie).join(MovieRating).filter(
		MovieRating.movie_id.not_in(movies_already_rated_ids) if movies_already_rated else True,
		MovieRating.ignored == 0).order_by(Movie.amount_of_ratings.desc()).distinct().all()
	# print("most rated movies:", most_rated_movies)

	# if the average ratings should not be considered, return the first amount_of_results results of the most rated
	# movies
	if consider_ratings is False:
		return most_rated_movies[:amount_of_results]

	# print("filter for liked movies")
	# extract all movies with an average rating of at least 4.0 from the most rated movies
	most_rated_popular_movies = [movie for movie in most_rated_movies if
	                             Movie.query.filter(Movie.id == movie.id).first().average_rating >= 4.0]

	return most_rated_popular_movies[:amount_of_results]


def get_all_rated_movies_by_current_user():
	"""
	Gets all movies the current user rated and their ratings of these movies.

	:return: all_rated_movies - list of Movie objects of all movies the current user rated,
			user_movie_rating - dictionary with movie ids as keys and the current user's ratings of the corresponding
			movies as values
	"""

	# get all movies the current user rated
	all_rated_movie_objects = (MovieRating.query.filter(MovieRating.user_id == current_user.id,
	                                                    MovieRating.rating.is_not(None)).all())

	# get the corresponding Movie objects and sort them by the time rated attribute in a descending manner (i.e. the
	# last rated movie first)
	all_rated_movie_objects_ids = [m.movie_id for m in all_rated_movie_objects]
	all_rated_movies = db.session.query(Movie).join(MovieRating).filter(
		MovieRating.movie_id.in_(all_rated_movie_objects_ids)).order_by(MovieRating.time_rated.desc()).all()

	# go through all movies to get and save the current user's rating of them in the dictionary
	user_movie_rating = {}
	for movie in all_rated_movie_objects:
		user_movie_rating[movie.movie_id] = movie.rating

	return all_rated_movies, user_movie_rating


def get_movie_genres(movie_id: int):
	"""
	Gets all genres of a movie.

	:param movie_id: id of the movie the genres should be gotten of
	:return: genres - list of the genres of the movie
	"""

	movie_genres = MovieGenre.query.filter(MovieGenre.movie_id == movie_id).all()
	genres = []
	for entry in movie_genres:
		genres.append(entry.genre)
	return genres


def get_genre_and_decade_filtered_recommendations(genre_filter: str, decade_filter: str, amount_of_results: int):
	"""
	Gets a set amount of movies from the database that the filters apply to.

	:param genre_filter: genre the result should be filtered by; can be empty
	:param decade_filter: decade the result should be filtered by; can be empty
	:param amount_of_results: amount of results that should be returned
	:return: filtered_movies - list of Movie objects that satisfy the filter conditions
	"""

	global all_movie_ids
	# get a list of all movie ids
	try:
		all_movie_ids
	except NameError:
		all_movie_ids = None
	if all_movie_ids is None:
		all_movie_ids, _ = get_all_movies_and_users_ids()

	# if both filtered are empty, return an empty list
	if len(genre_filter) == 0 and len(decade_filter) == 0:
		return []
	# print("filter:", genre_filter, decade_filter)

	# get a list of the ids of all movies the current user rated, excluding those they ignored
	movies_already_rated = MovieRating.query.filter(MovieRating.user_id == current_user.id,
	                                                MovieRating.ignored == 0).all()
	movies_already_rated_ids = [m.movie_id for m in movies_already_rated]
	# get a list of the ids of all movies the current user ignored
	ignored_movies = MovieRating.query.filter(MovieRating.user_id == current_user.id,
	                                          MovieRating.ignored == 1).all()
	ignored_movies_ids = [m.movie_id for m in ignored_movies]

	# get a list of all movie ids sorted by their total recommendation score in a descending manner to be able to
	# sort the filtered movies accordingly
	recommended_movies = UserMovieRecommendationScores.query.filter(
		UserMovieRecommendationScores.user_id == current_user.id).order_by(
		UserMovieRecommendationScores.total_recommendation_score.desc()).all()
	recommended_movies_ids = [m.movie_id for m in recommended_movies]
	id_ordering = case(
		{_id: index for index, _id in enumerate(recommended_movies_ids)},
		value=Movie.id
		)

	# if both filters are set, filter the Movie entries by both filters and exclude ignored and rated movies
	if len(genre_filter) > 0 and len(decade_filter) > 0:
		# convert the decade filter ("XXXXs") into an int
		decade = int(decade_filter[:4])
		# get the possible release years corresponding to the decade (XXX0-XXX9)
		possible_years = [y for y in range(decade, decade + 10)]
		filtered_movies = (Movie.query.filter(Movie.genres.any(MovieGenre.genre == genre_filter),
		                                      Movie.release_year.in_(possible_years),
		                                      Movie.id.not_in(movies_already_rated_ids),
		                                      Movie.id.not_in(ignored_movies_ids)).order_by(id_ordering)
		                   .limit(amount_of_results).all())
	# if only the genre filter is set, filter the Movie entries by the genre filter and exclude ignored and rated movies
	elif len(genre_filter) > 0 and len(decade_filter) == 0:
		filtered_movies = (Movie.query.filter(Movie.genres.any(MovieGenre.genre == genre_filter),
		                                      Movie.id.not_in(movies_already_rated_ids),
		                                      Movie.id.not_in(ignored_movies_ids)).order_by(id_ordering)
		                   .limit(amount_of_results).all())
	# else only the decade filter is set; filter the Movie entries by the decade filter and exclude ignored and rated
	# movies
	else:
		# convert the decade filter ("XXXXs") into an int
		decade = int(decade_filter[:4])
		# get the possible release years corresponding to the decade (XXX0-XXX9)
		possible_years = [y for y in range(decade, decade + 10)]
		filtered_movies = (Movie.query.filter(Movie.release_year.in_(possible_years),
		                                      Movie.id.not_in(movies_already_rated_ids),
		                                      Movie.id.not_in(ignored_movies_ids)).order_by(id_ordering)
		                   .limit(amount_of_results).all())

	return filtered_movies


def get_movies_on_watchlist():
	"""
	Gets all movies the current user added to their watchlist.

	:return: movies_on_watchlist - list of Movie objects of the movies the current user added to their watchlist or
			[ ] if there are none
	"""

	# get all movies the current user added to their watchlist by filtering the database and order it by the time the
	# user added the movies to the watchlist in a descending manner (i.e. most recent first)
	movies_on_watchlist = (db.session.query(Movie).join(MovieWatchList)
	                       .filter(MovieWatchList.user_id == current_user.id)
	                       .order_by(MovieWatchList.time_added.desc()).all())

	# if there are no entries, return an empty list instead
	return movies_on_watchlist if movies_on_watchlist else []


def get_ignored_movies():
	"""
	Gets all movies the current user ignored.

	:return: ignored_movies - list of Movie objects of the movies the current users ignored or [ ] if there are none
	"""
	ignored_movies = (db.session.query(Movie).join(MovieRating)
	                  .filter(MovieRating.user_id == current_user.id, MovieRating.ignored == 1)
	                  .order_by(MovieRating.time_ignored.desc()).all())
	return ignored_movies if ignored_movies else []


def get_survey_preferences():
	"""
	Gets the preferences of the current user as selected in the preference survey.

	:return: liked genres - list of all genres the user selected as liked,
			disliked_genres - list of all genres the user selected as disliked
	"""

	# get the preferences by filtering the database with the survey_response attribute
	liked_genres = UserGenrePreferences.query.filter(UserGenrePreferences.user_id == current_user.id,
	                                                 UserGenrePreferences.survey_response == 1).all()
	liked_genres = [liked.genre for liked in liked_genres]
	disliked_genres = UserGenrePreferences.query.filter(UserGenrePreferences.user_id == current_user.id,
	                                                    UserGenrePreferences.survey_response == 0).all()
	disliked_genres = [disliked.genre for disliked in disliked_genres]

	return liked_genres, disliked_genres


def get_user_preferences_from_database(min_ratio: float):
	"""
	Gets the preferences of the current user that can be assumed from their ratings.

	:param min_ratio: minimum ratio that is needed so that a ratio is deemed as a liked/disliked preference
	:return: extracted_liked_genres, extracted_disliked_genres, extracted_liked_decades, extracted_disliked_decades -
			lists of genres and decades that can be assumed as preferences of the current user based on their ratings
	"""

	# get the genre and decade ratios with minimum amount of ratings 4
	genre_ratios, decade_ratios = get_user_preference_ratios(4)
	extracted_liked_genres = []
	extracted_disliked_genres = []
	# go through all genres
	for genre in genre_ratios.keys():
		# if the liked ratio is at least the min ratio, append the genre to the liked genre list
		if genre_ratios[genre][0] >= min_ratio:
			extracted_liked_genres.append(genre)
		# if the disliked ratio is at least the min ratio, append the genre to the disliked genre list
		elif genre_ratios[genre][1] >= min_ratio:
			extracted_disliked_genres.append(genre)
	extracted_liked_decades = []
	extracted_disliked_decades = []
	# go through all decades
	for decade in decade_ratios.keys():
		# if the liked ratio is at least the min ratio, append the decade to the liked decades list
		if decade_ratios[decade][0] >= min_ratio:
			extracted_liked_decades.append(decade)
		# if the disliked ratio is at least the min ratio, append the decade to the disliked decades list
		elif decade_ratios[decade][1] >= min_ratio:
			extracted_disliked_decades.append(decade)

	return extracted_liked_genres, extracted_disliked_genres, extracted_liked_decades, extracted_disliked_decades


def get_user_preference_ratios(min_amount_of_ratings: int):
	"""
	Gets the preferences of the current user as saved in UserGenrePreferences and UserDecadePreferences.

	:param min_amount_of_ratings: amount of ratings needed for a genre/decade so that the saved preferences are
			considered as preferences
	:return: genre_rating_ratios - dictionary with genres as keys and a list of the corresponding liked and disliked
			percentages as decimals,
			decade_rating_ratios - dictionary with decades as keys and a list of the corresponding liked and disliked
			percentages as decimals
	"""

	genre_rating_ratios = {}
	# go through all genres in the database
	for genre in get_all_movie_genres():
		if genre is not None:
			# get the UserGenrePreference entry for the genre corresponding to the current user
			row = UserGenrePreferences.query.filter(UserGenrePreferences.user_id == current_user.id,
			                                        UserGenrePreferences.genre == genre).first()
			# if no entry exists (which could be the case if the current user did not submit the preference survey and
			# did not rate a movie yet), add a new entry and set the genre ratios to 0.0
			if not row:
				new_genre_preference = UserGenrePreferences(user_id=current_user.id, genre=genre,
				                                            survey_response=math.nan, amount_of_ratings=0,
				                                            amount_of_likes=0, amount_of_dislikes=0)
				db.session.add(new_genre_preference)
				db.session.commit()
				genre_rating_ratios[genre] = [0.0, 0.0]
			# if the entry exists, check the amount of ratings for the genre
			else:
				# if the amount is less than the minimum amount of ratings, set the genre ratios to 0.0
				if row.amount_of_ratings < min_amount_of_ratings:
					genre_rating_ratios[genre] = [0.0, 0.0]
				# if the amount is at least the minimum amount of ratings, calculate the genre ratios
				else:
					genre_rating_ratios[genre] = [
						row.amount_of_likes / row.amount_of_ratings,
						row.amount_of_dislikes / row.amount_of_ratings
						]

	decade_rating_ratios = {}
	# go through all decades from the 1900's to the 2020's
	for decade in range(1900, 2030, 10):
		# get the UserDecadePreference entry for the decade corresponding to the current user
		row = UserDecadePreferences.query.filter(UserDecadePreferences.user_id == current_user.id,
		                                         UserDecadePreferences.decade == decade).first()
		# if no entry exists (which could be the case if the current user did not submit the preference survey and
		# did not rate a movie yet), add a new entry and set the decade ratios to 0.0
		if not row:
			new_decade_preference = UserDecadePreferences(user_id=current_user.id, decade=decade, amount_of_ratings=0,
			                                              amount_of_likes=0, amount_of_dislikes=0)
			db.session.add(new_decade_preference)
			db.session.commit()
			decade_rating_ratios[decade] = [0.0, 0.0]
		# if the entry exists, check the amount of ratings for the decade
		else:
			# if the amount is less than the minimum amount of ratings, set the decade ratios to 0.0
			if row.amount_of_ratings < min_amount_of_ratings:
				decade_rating_ratios[decade] = [0.0, 0.0]
			# if the amount is at least the minimum amount of ratings, calculate the decade ratios
			else:
				decade_rating_ratios[decade] = [
					row.amount_of_likes / row.amount_of_ratings,
					row.amount_of_dislikes / row.amount_of_ratings
					]

	return genre_rating_ratios, decade_rating_ratios
