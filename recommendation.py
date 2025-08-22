from flask_user import current_user
from sqlalchemy import and_, or_, case, Table, Column, func, exc
from sklearn.metrics.pairwise import nan_euclidean_distances
import numpy
import calendar
import time
import math

from get_data import (get_user_preference_ratios, get_all_movies_and_users_ids, get_most_popular_movies,
                      get_movie_genres, get_survey_preferences, get_all_rated_movies_by_current_user,
                      get_all_rated_movies_ids)
from models import (db, Movie, MovieRating, UserGenrePreferences, UserDecadePreferences, MovieWatchList,
                    UserMovieRecommendationScores)
from utils import check_whether_there_are_survey_entries

global all_movie_ids_rated, all_movie_ids, all_user_ids


# set the allowed values for the recommendation type
recommendation_types = ["user-based", "item-based", "explorative", "hybrid", "survey-based"]


def get_movie_recommendations(min_amount_of_ratings: int, min_rating: float, amount_of_results: int,
                              method: str = "hybrid", calculation_needed_for: tuple[str] =
                              ('user-based', 'item-based', 'explorative', 'hybrid', 'survey-based')):
	"""
	Gets the movie recommendations and updates the score attributes in UserMovieRecommendationScores if needed.

	:param min_amount_of_ratings: minimum amount of ratings needed to get user-based, item-based and hybrid recommendations
	:param min_rating: minimum rating needed so that a movie is deemed as liked
	:param amount_of_results: amount of results that should be returned
	:param method: method that should be used for the recommendations
	:param calculation_needed_for: tuple of strings relating to UserMovieRecommendationScores attributes that the values
			need to be recalculated for
	:return: user_based_recommendations if method == "user-based" - list of Movie objects of user-based movie
			recommendations,
			item_based_recommendations if method == "item-based",
			survey_based_recommendations if method == "survey-based",
			exploration_based_recommendations if method == "explorative",
			hybrid_recommendations if method == "hybrid" - list of Movie objects corresponding to the movie recommendations
			based on the method
	"""

	# check if the method is valid
	if method not in recommendation_types:
		raise ValueError("Invalid value for parameter method. Expected one of: %s" % recommendation_types)

	# get a list of the ids of all movies the current user rated, excluding those they ignored
	movies_already_rated = MovieRating.query.filter(MovieRating.user_id == current_user.id,
	                                                MovieRating.ignored == 0).all()
	# if calculation_needed_for:
	# print("get movie recommendations called with calculation needed for ", calculation_needed_for)
	# else:
	# print("get movie recommendations called with no calculation needed")

	# print("amount of movies the user rated:", len(movies_already_rated))
	# check how much history there is for the current user
	# if the current user rated fewer movies than min_amount_of_ratings, use the survey responses for the recommendations
	# if there are no survey responses, use the explorative method instead
	if len(movies_already_rated) < min_amount_of_ratings:
		method = "survey-based" if check_whether_there_are_survey_entries() else "explorative"
	# print("method is", method, "as there are not enough ratings yet")
	# if the user rated at least min_amount_of_ratings movies, get user-based, item-based and explorative
	# recommendations based on them
	else:
		# region USER-BASED
		# user-based recommendations: get movies that similar users liked that the user did not rate yet
		# print("USER-BASED")

		# if user-based is part of the recalculation tuple, recalculate the user-based scores
		if 'user-based' in calculation_needed_for:
			calculate_user_based_scores(min_rating)

		# if the method is user-based, get user-based recommendations and return
		if method == "user-based":
			user_based_recommendations = get_user_based_recommendations(amount_of_results)
			return user_based_recommendations
		# endregion

		# region ITEM-BASED
		# item-based recommendations: get movies that have similar properties to the movies the user liked
		# print("ITEM-BASED")

		# if item-based is part of the recalculation tuple, recalculate the item-based scores
		if 'item-based' in calculation_needed_for:
			# print("will get preference ratios")
			# get the genre and decade ratios
			genre_ratios, decade_ratios = get_user_preference_ratios(1)
			calculate_item_based_scores(genre_ratios, decade_ratios)

		# if the method is item-based, get item-based recommendations and return
		if method == "item-based":
			item_based_recommendations = get_item_based_recommendations(amount_of_results)
			return item_based_recommendations
	# endregion

	# region SURVEY-BASED
	# survey-based: get movies fitting the preferences selected in the survey
	# print("SURVEY-BASED")
	# if there are survey entries, check whether recalculation is needed and survey-based recommendations should be
	# returned
	if check_whether_there_are_survey_entries():
		# print("there are survey entries")
		# if survey-based is part of the recalculation tuple, recalculate the survey-based scores
		if 'survey-based' in calculation_needed_for:
			calculate_survey_based_scores()

		# if the method is survey-based, get survey-based recommendations and return
		if method == "survey-based":
			survey_based_recommendations = get_survey_based_recommendations(amount_of_results)
			return survey_based_recommendations
	# if there are no survey entries, update the survey based score attribute to 0.0 if there were previous survey
	# responses
	else:
		# reset survey-based scores if they were calculated for previous responses
		if UserMovieRecommendationScores.query.filter(
				UserMovieRecommendationScores.user_id == current_user.id,
				UserMovieRecommendationScores.survey_based_score != 0).all():
			# print("reset survey-based movie scores from previous survey responses")
			(db.session.query(UserMovieRecommendationScores).filter(
				UserMovieRecommendationScores.user_id == current_user.id).update(
				{'survey_based_score': 0.0}))
			db.session.commit()
	# endregion

	# region EXPLORATIVE
	# exploration-based recommendations: get additional recommendations that are not based on similar users or similar
	# items
	# if user did not rate at least 50 movies, recommendations are popular and liked movies
	# if they did rate at least 50 movies, underexplored genres
	# should be explored
	# print("EXPLORATIVE")

	# if explorative is part of the recalculation tuple, recalculate the exploration-based recommendations
	if 'explorative' in calculation_needed_for:
		# if the current user rated less than 50 movies, base the score on popularity
		if len(movies_already_rated) < 50:
			calculate_exploration_based_scores("popular")
		# if the current user rated at least 50 movies, base the score on under-exploration
		else:
			calculate_exploration_based_scores("underexplored")

	# if the method is explorative, get exploration-based recommendations and return
	if method == "explorative":
		exploration_based_recommendations = get_exploration_based_recommendations(amount_of_results)
		return exploration_based_recommendations
	# endregion

	# region HYBRID
	# hybrid recommendations: get movies that fit the survey, that similar users liked, that are similar to liked
	# movies, and that allow for exploration (weighted scores)
	# print("HYBRID")

	# if hybrid is part of the recalculation tuple, recalculate the total recommendation scores
	if 'hybrid' in calculation_needed_for:
		calculate_hybrid_scores()

	# if the method is hybrid, get hybrid recommendations and return
	if method == "hybrid":
		hybrid_recommendations = get_hybrid_recommendations(amount_of_results)
		return hybrid_recommendations


# region exploration-based
# set the values allowed for the exploration type parameter
exploration_types = ["popular", "underexplored"]


def calculate_exploration_based_scores(exploration_type: str):
	"""
	Calculates the exploration_based_score attribute of UserMovieRecommendationScores corresponding to the current
	user. The score depends on either the popularity of the corresponding movie in terms of the amount of ratings and
	its average movie rating, or on how many of the corresponding movie's genres are underexplored by the current user.

	:param exploration_type: either popular or underexplored, with the latter meaning that the current user did not
			rate any or very few movies of the respective genre(s)
	"""

	# get the ids of all movies
	global all_movie_ids
	try:
		all_movie_ids
	except NameError:
		all_movie_ids = None
	if all_movie_ids is None:
		all_movie_ids, _ = get_all_movies_and_users_ids()

	# validate the parameter
	if exploration_type not in exploration_types:
		raise ValueError("Invalid value for parameter method. Expected one of: %s" % exploration_types)

	# get a list of the ids of all movies the current user rated, excluding those they ignored
	movies_already_rated = MovieRating.query.filter(MovieRating.user_id == current_user.id,
	                                                MovieRating.ignored == 0).all()
	movies_already_rated_ids = [m.movie_id for m in movies_already_rated]
	# get a list of the ids of all movies the current user ignored
	ignored_movies = MovieRating.query.filter(MovieRating.user_id == current_user.id,
	                                          MovieRating.ignored == 1).all()
	ignored_movies_ids = [m.movie_id for m in ignored_movies]

	# get the maximum amount of ratings in the database
	max_amount_of_ratings = db.session.query(func.max(Movie.amount_of_ratings)).first()[0]

	# if the exploration type if popular, the score depends on the movies' popularity
	if exploration_type == "popular":
		# print("POPULAR MOVIES")
		# get the 100 most popular movies
		popular_liked_movies = get_most_popular_movies(100, consider_ratings=True)
		popular_liked_movies_ids = [m.id for m in popular_liked_movies]
		# from all movie ids, extract those that are not part of the popular movies
		remainder_movies = [m_id for m_id in all_movie_ids if m_id not in popular_liked_movies_ids]

		# print("go through popular movies and calculate score based on average rating")
		new_scores = {}
		# go through all popular movies
		for movie in popular_liked_movies:
			# if the current user ignored or rated the movie, set the score to 0.0
			if movie.id in ignored_movies_ids or movie.id in movies_already_rated_ids:
				score = 0.0
			# else, calculate the score of the movie
			else:
				# get the amount of ratings of the movie
				amount_of_ratings = Movie.query.filter(Movie.id == movie.id).first().amount_of_ratings
				# if it is None, set it to 0
				if amount_of_ratings is None:
					amount_of_ratings = 0
				# get the average rating of the movie
				average_movie_rating = Movie.query.filter(Movie.id == movie.id).first().average_rating
				# half of the score is a factor determined by casting the amount of ratings of the movie
				# to the score range from 0.0 to 1.0
				# the other half is the average score of the movie casted to the rating range from 0.0 to 1.0
				# with the rating range of the popular movies being (4.0, 5.0) and the score range being (0.0, 1.0),
				# the calculation is:
				# ((average_rating - min_rating_range) / (max_rating_range - min_rating_range)) +
				# (max_score_range - min_score_range) + min_score_range
				# = ((average_rating - 4.0) / 5.0 - 4.0)) + (1.0 - 0.0) + 0.0
				# so simplified: (average_rating - 4.0)
				score = round(
					(0.5 * (average_movie_rating - 4.0) + 0.5 * (amount_of_ratings / max_amount_of_ratings)), 2)
			# append the score to the dictionary
			new_scores[movie.id] = score
		# set the score of all movies that are not part of the popular movies to 0.0
		for movie in remainder_movies:
			new_scores[movie] = 0.0
	# if the exploration type is underexplored, the score depends on whether the current user did rate none or few
	# movies with the corresponding genre
	elif exploration_type == "underexplored":
		# print("UNDEREXPLORED GENRES")
		underexplored_genres = []
		# print("get genres with no ratings by the user")
		# get all genres that the user did not rate any movie with yet
		no_ratings = UserGenrePreferences.query.filter(
			UserGenrePreferences.user_id == current_user.id,
			UserGenrePreferences.amount_of_ratings == 0
			).all()
		# if there are such genres, append them to the list
		if no_ratings:
			for g in no_ratings:
				underexplored_genres.append(g.genre)
		# if there are none, get underexplored genres, i.e. less than 10% of the current user's ratings included these
		# genres
		else:
			# print("None found; get genres with amount of ratings less than 10% of total amount of ratings of the user")
			few_ratings = UserGenrePreferences.query.filter(
				UserGenrePreferences.user_id == current_user.id,
				UserGenrePreferences.amount_of_ratings < len(movies_already_rated_ids) * 0.1
				).all()
			for g in few_ratings:
				underexplored_genres.append(g.genre)

		# print("underexplored genres:", underexplored_genres)

		# if there are underexplored genres, calculate the score based on the proportion of underexplored genres of all
		# movie genres for a movie
		if underexplored_genres:
			# print("go through all movies and calculate their score")
			# count = 0
			new_scores = {}
			# go through all movies
			for movie in all_movie_ids:
				# count += 1
				# if count % 1000 == 0:
				# print("loop count:", count)
				# if count == len(all_movie_ids):
				# print("last loop")
				# if the current user ignored or rated the movie, set the score to 0.0
				if movie in ignored_movies_ids or movie in movies_already_rated_ids:
					score = 0.0
				# else, calculate the score
				else:
					# get all genres of the movie
					movie_genres = get_movie_genres(movie)
					amount_of_genres = len(movie_genres)
					# if no genre is listed, add a small score for recommendation to not exclude it
					if None in movie_genres:
						score = 0.25
					else:
						# extract the underexplored genres from the movie genres
						underexplored = [g for g in movie_genres if g is not None and g in underexplored_genres]
						# if there is at least one, calculate the score as a proportion
						if underexplored:
							score = round(len(underexplored) / amount_of_genres, 2)
						# if none of the genres is underexplored, set the score to 0.0
						else:
							score = 0.0
				# append the score to the dictionary
				new_scores[movie] = score
		# if there are no underexplored genres, set the score of each movie to 0.0 (rather unlikely for the current
		# context)
		else:
			# print("there are no underexplored genres")
			new_scores = {}
			for movie in all_movie_ids:
				new_scores[movie] = 0.0
	else:
		raise ValueError("Invalid value for parameter method. Expected one of: %s" % exploration_types)

	# create a temporary table
	try:
		temp = Table("temp", db.metadata,
		             Column("movie_id", db.Integer),
		             Column("exploration_based_score", db.Float),
		             extend_existing=True
		             )
	except exc.InvalidRequestError:
		temp = None
	if temp is None:
		temp = Table("temp", db.metadata,
		             Column("movie_id", db.Integer),
		             Column("exploration_based_score", db.Float),
		             extend_existing=True
		             )
	db.session.commit()
	temp.create(bind=db.session.get_bind())

	# insert the new scores
	db.session.execute(
		temp.insert().values(
			[{"movie_id": k, "exploration_based_score": v} for k, v in new_scores.items()]))

	# update the UserMovieRecommendationScores corresponding to the current user
	db.session.execute(UserMovieRecommendationScores.__table__.update().values(
		exploration_based_score=temp.c.exploration_based_score).where(and_(
		UserMovieRecommendationScores.__table__.c.movie_id == temp.c.movie_id,
		UserMovieRecommendationScores.__table__.c.user_id == current_user.id)))
	db.session.commit()

	# drop the temporary table
	temp.drop(bind=db.session.get_bind())


def get_exploration_based_recommendations(amount_of_results: int):
	"""
	Gets a set amount of movie recommendations based on the exploration based score attribute in
	UserMovieRecommendationsScores.

	:param amount_of_results: amount of results that should be returned
	:return: exploration_based_recommendations = list of Movie objects of the recommended movies
	"""

	# get movies by score from the database
	# print("get exploration based recommendations by filtering the database")
	# sort the UserMovieRecommendationScores entries corresponding to the current user by the exploration based score
	# attribute in a descending manner and get the first amount_of_results entries and the corresponding movie ids
	exploration_based_recommendations_ids = UserMovieRecommendationScores.query.filter(
		UserMovieRecommendationScores.user_id == current_user.id
		).order_by(UserMovieRecommendationScores.exploration_based_score.desc()).limit(amount_of_results).all()

	exploration_based_recommendations_ids = [m.movie_id for m in exploration_based_recommendations_ids]

	id_ordering = case(
		{_id: index for index, _id in enumerate(exploration_based_recommendations_ids)},
		value=Movie.id
		)

	# print("get corresponding Movie Objects")
	# get the corresponding Movie objects ordered by the exploration based score attribute
	exploration_based_recommendations = Movie.query.filter(
		Movie.id.in_(exploration_based_recommendations_ids),
		).order_by(id_ordering).all()

	return exploration_based_recommendations
# endregion


# region survey
def save_survey_preferences_and_check_for_recalculation(included_genres: list[str], excluded_genres: list[str]):
	"""
	Adds the preference survey responses of the current user to the database and checks if and which score
	recalculations are necessary for the movie recommendations.

	:param included_genres: list of genres the current user selected as liked in the preference survey
	:param excluded_genres: list of genres the current user selected as disliked in the preference survey
	:return: recalculation_needed_for - tuple of strings referring to which scores need to be recalculated for the movie
			recommendations
	"""

	# get UserGenrePreferences entries which survey responses are saved for
	previous_response_rows = UserGenrePreferences.query.filter(UserGenrePreferences.user_id == current_user.id,
	                                                           or_(UserGenrePreferences.survey_response == 0,
	                                                               UserGenrePreferences.survey_response == 1)).all()
	# if there are previous responses and/or at least one of the lists is not empty, the movie scores need to be
	# recalculated
	if previous_response_rows or (included_genres is not [] or excluded_genres is not []):
		recalculation_needed_for = ('survey-based', 'hybrid')
	# else (there are no previous responses and both lists are empty) no recalculation is needed
	else:
		recalculation_needed_for = ()
	# reset the rows that have survey responses saved
	# if previous_response_rows:
	# print("delete previous survey responses from database")
	for row in previous_response_rows:
		setattr(row, 'survey_response', math.nan)
		db.session.commit()

	# print("save survey preferences to database")
	# save the (new) survey responses
	# go through each genre the current user selected as liked
	for genre in included_genres:
		# get the UserGenrePreference entry of the genre corresponding to the current user
		row = UserGenrePreferences.query.filter(UserGenrePreferences.user_id == current_user.id,
		                                        UserGenrePreferences.genre == genre).first()
		# if an entry exists (which would be the case if the home page was loaded before the survey was submitted),
		# update the survey response attribute to 1 (i.e. "include")
		if row:
			setattr(row, 'survey_response', 1)
			db.session.commit()
		# if no entry exists (which would be the case if the current user submitted the survey before having rated a
		# movie), add a new entry
		else:
			new_entry = UserGenrePreferences(user_id=current_user.id, genre=genre, survey_response=1,
			                                 amount_of_ratings=0, amount_of_likes=0, amount_of_dislikes=0)
			db.session.add(new_entry)
			db.session.commit()
	# go through each genre the current user selected as liked
	for genre in excluded_genres:
		# get the UserGenrePreference entry of the genre corresponding to the current user
		row = UserGenrePreferences.query.filter(UserGenrePreferences.user_id == current_user.id,
		                                        UserGenrePreferences.genre == genre).first()
		# if an entry exists (which would be the case if the current user rated a movie before submitting the survey),
		# update the survey response attribute to 0 (i.e. "exclude")
		if row:
			setattr(row, 'survey_response', 0)
			db.session.commit()
		# if no entry exists (which would be the case if the survey was submitted before the home page was loaded), add
		# a new entry
		else:
			new_entry = UserGenrePreferences(user_id=current_user.id, genre=genre, survey_response=0,
			                                 amount_of_ratings=0, amount_of_likes=0, amount_of_dislikes=0)
			db.session.add(new_entry)
			db.session.commit()

	return recalculation_needed_for
# endregion


# region survey-based
def calculate_survey_based_scores():
	"""
	Calculates the survey_based_score attribute of UserMovieRecommendationScores corresponding to the current user. The
	score depends on how many of the genres of the corresponding movie the user selected as liked in the preference
	survey.
	"""

	global all_movie_ids
	try:
		all_movie_ids
	except NameError:
		all_movie_ids = None
	if all_movie_ids is None:
		all_movie_ids, _ = get_all_movies_and_users_ids()

	# get a list of the ids of all movies the current user rated, excluding those they ignored
	movies_already_rated = MovieRating.query.filter(MovieRating.user_id == current_user.id,
	                                                MovieRating.ignored == 0).all()
	movies_already_rated_ids = [m.movie_id for m in movies_already_rated]
	# get a list of the ids of all movies the current user ignored
	ignored_movies = MovieRating.query.filter(MovieRating.user_id == current_user.id,
	                                          MovieRating.ignored == 1).all()
	ignored_movies_ids = [m.movie_id for m in ignored_movies]

	# get the maximum amount of ratings from the database
	max_amount_of_ratings = db.session.query(func.max(Movie.amount_of_ratings)).first()[0]

	# print("get survey preferences")
	# get the preferences the current user selected in the preference survey
	liked_genres, disliked_genres = get_survey_preferences()

	# print("go through all movies to calculate the score")
	# count = 0
	new_scores = {}
	# go through all movies
	for movie in all_movie_ids:
		# count += 1
		# if count % 1000 == 0:
		# print("loop count:", count)
		# if count == len(all_movie_ids):
		# print("last loop")
		# if the current user ignored or rated the movie, set the score to 0.0
		if movie in ignored_movies_ids or movie in movies_already_rated_ids:
			score = 0.0
		else:
			# get the genres of the movie
			movie_genres = get_movie_genres(movie)
			# extract those genres the current user selected as disliked in the preference survey
			disliked = [g for g in movie_genres if g in disliked_genres]
			# if at least one of the movie genres was specified as disliked, set the score to 0.0
			if disliked:
				score = 0.0
			# if none of the genres was specified as disliked, extract those genres the current user selected as liked
			# in the preference survey
			else:
				liked = [g for g in movie_genres if g in liked_genres]
				# if at least one of the movie genres was specified as liked, calculate the score of the movie
				if liked:
					# get the amount of ratings for the movie
					amount_of_ratings = Movie.query.filter(Movie.id == movie).first().amount_of_ratings
					# if it is None, set it to 0
					if amount_of_ratings is None:
						amount_of_ratings = 0
					# half of the score is a factor determined by casting the amount of ratings of the movie
					# to the score range from 0.0 to 1.0
					# with the rating range being (0, max_amount_of_ratings) and the score range being (0.0, 1.0),
					# the calculation is:
					# ((amount_of_ratings - min_rating_range) / (max_rating_range - min_rating_range)) +
					# (max_score_range - min_score_range) + min_score_range
					# = ((amount_of_ratings - 0 / max_amount_of_ratings - 0)) + (1.0 - 0.0) + 0.0
					# so simplified: (amount_of_ratings / max_amount_of_ratings)
					score = round((0.5 * (len(liked) / len(movie_genres)) + 0.5 * (
							amount_of_ratings / max_amount_of_ratings)), 2)
				# if none of the movie genres was either disliked or liked, set the score to 0.0
				else:
					score = 0.0
		# append the score to the dictionary
		new_scores[movie] = score
	# create a temporary table
	try:
		temp = Table("temp", db.metadata,
		             Column("movie_id", db.Integer),
		             Column("survey_based_score", db.Float),
		             extend_existing=True
		             )
	except exc.InvalidRequestError:
		temp = None
	if temp is None:
		temp = Table("temp", db.metadata,
		             Column("movie_id", db.Integer),
		             Column("survey_based_score", db.Float),
		             extend_existing=True
		             )
	db.session.commit()
	temp.create(bind=db.session.get_bind())

	# insert the new movie scores
	db.session.execute(
		temp.insert().values([{"movie_id": k, "survey_based_score": v} for k, v in new_scores.items()]))

	# update the UserMovieRecommendationScores entries corresponding to the current user
	db.session.execute(UserMovieRecommendationScores.__table__.update().values(
		survey_based_score=temp.c.survey_based_score).where(and_(
		UserMovieRecommendationScores.__table__.c.movie_id == temp.c.movie_id,
		UserMovieRecommendationScores.__table__.c.user_id == current_user.id)))
	db.session.commit()

	# drop the temporary table
	temp.drop(bind=db.session.get_bind())


def get_survey_based_recommendations(amount_of_results: int):
	"""
	Gets a set amount of movie recommendations based on the survey based score attribute in
	UserMovieRecommendationsScores.

	:param amount_of_results: amount of results that should be returned
	:return: survey_based_recommendations = list of Movie objects of the recommended movies
	"""

	# print("get survey-based recommendations by filtering the database")
	# sort the UserMovieRecommendationScores entries corresponding to the current user by the item based score attribute
	# in a descending manner and get the first amount_of_results entries and the corresponding movie ids
	survey_based_recommendations = UserMovieRecommendationScores.query.filter(
		UserMovieRecommendationScores.user_id == current_user.id
		).order_by(UserMovieRecommendationScores.survey_based_score.desc()).limit(amount_of_results).all()

	survey_based_recommendation_ids = [m.movie_id for m in survey_based_recommendations]

	id_ordering = case(
		{_id: index for index, _id in enumerate(survey_based_recommendation_ids)},
		value=Movie.id
		)

	# print("get movie objects")
	# get the corresponding Movie objects ordered by the survey based score attribute
	survey_based_recommendations = Movie.query.filter(Movie.id.in_(survey_based_recommendation_ids)).order_by(
		id_ordering).all()

	return survey_based_recommendations
# endregion


# region user preferences
def add_or_update_user_preferences(movie_id: int, movie_rating: float):
	"""
	Updates UserGenrePreferences and UserDecadePreferences entries corresponding to a movie and the current user
	based on the current user's rating of the movie.

	:param movie_id: id of the movie the corresponding UserGenrePreferences and UserDecadePreferences entries should
			be updated for
	:param movie_rating: the current user's rating of the movie
	"""

	# get the genres of the movie
	genres = get_movie_genres(movie_id)
	# go through each genre
	for genre in genres:
		if genre is None:
			continue
		# get the UserGenrePreference entry for the genre corresponding to the current user
		row = UserGenrePreferences.query.filter(UserGenrePreferences.user_id == current_user.id,
		                                        UserGenrePreferences.genre == genre).first()
		# if the entry exists, update the attributes
		if row:
			# increase the amount of ratings by 1
			setattr(row, 'amount_of_ratings', UserGenrePreferences.amount_of_ratings + 1)
			db.session.commit()
			# if the movie was liked, increase the amount of liked movies by 1
			if movie_rating > 3.5:
				setattr(row, 'amount_of_likes', UserGenrePreferences.amount_of_likes + 1)
				db.session.commit()
			# if the movie was disliked, increase the amount of disliked movies by 1 instead
			elif movie_rating < 2.5:
				setattr(row, 'amount_of_dislikes', UserGenrePreferences.amount_of_dislikes + 1)
				db.session.commit()
		# if no entry exists, add a new entry with the corresponding values depending on the rating and the survey
		# response attribute to NaN as the entry would have existed if there were survey entries by the current user
		else:
			if movie_rating > 3.5:
				new_entry = UserGenrePreferences(user_id=current_user.id, genre=genre, survey_response=math.nan,
				                                 amount_of_ratings=1, amount_of_likes=1, amount_of_dislikes=0)
				db.session.add(new_entry)
				db.session.commit()
			elif movie_rating < 2.5:
				new_entry = UserGenrePreferences(user_id=current_user.id, genre=genre, survey_response=math.nan,
				                                 amount_of_ratings=1, amount_of_likes=0, amount_of_dislikes=1)
				db.session.add(new_entry)
				db.session.commit()
			# if the movie was neither liked nor disliked, set only the amount of ratings to 1
			else:
				new_entry = UserGenrePreferences(user_id=current_user.id, genre=genre, survey_response=math.nan,
				                                 amount_of_ratings=1, amount_of_likes=0, amount_of_dislikes=0)
				db.session.add(new_entry)
				db.session.commit()

	# get the release year of the movie
	year = Movie.query.filter(Movie.id == movie_id).first().release_year
	if year is not None:
		# get the corresponding decade
		decade = math.floor(year / 10) * 10
		# get the UserDecadePreference entry for the decade corresponding to the current user
		row = UserDecadePreferences.query.filter(UserDecadePreferences.user_id == current_user.id,
		                                         UserDecadePreferences.decade == decade).first()
		# if the entry exists, update the attributes
		if row:
			# increase the amount of ratings by 1
			setattr(row, 'amount_of_ratings', UserDecadePreferences.amount_of_ratings + 1)
			db.session.commit()
			# if the movie was liked, increase the amount of liked movies by 1
			if movie_rating > 3.5:
				setattr(row, 'amount_of_likes', UserDecadePreferences.amount_of_likes + 1)
				db.session.commit()
			# if the movie was disliked, increase the amount of disliked movies by 1 instead
			elif movie_rating < 2.5:
				setattr(row, 'amount_of_dislikes', UserDecadePreferences.amount_of_dislikes + 1)
				db.session.commit()
		# if no entry exists, add a new entry with the corresponding values depending on the rating and the survey
		# response attribute to NaN as the entry would have existed if there were survey entries by the current user
		else:
			if movie_rating > 3.5:
				new_decade_preference = UserDecadePreferences(user_id=current_user.id, decade=decade,
				                                              amount_of_ratings=1,
				                                              amount_of_likes=1, amount_of_dislikes=0)
				db.session.add(new_decade_preference)
				db.session.commit()
			elif movie_rating < 2.5:
				new_decade_preference = UserDecadePreferences(user_id=current_user.id, decade=decade,
				                                              amount_of_ratings=1,
				                                              amount_of_likes=0, amount_of_dislikes=1)
				db.session.add(new_decade_preference)
				db.session.commit()
			# if the movie was neither liked nor disliked, set only the amount of ratings to 1
			else:
				new_decade_preference = UserDecadePreferences(user_id=current_user.id, decade=decade,
				                                              amount_of_ratings=1,
				                                              amount_of_likes=0, amount_of_dislikes=0)
				db.session.add(new_decade_preference)
				db.session.commit()
# endregion


# region user-based
def calculate_euclidean_distance_between_vectors(vector1: list[float], vector2: list[float]):
	"""
	Calculates the euclidean distance between two vectors.

	:param vector1: first vector
	:param vector2: second vector
	:return: euclidean_distance - euclidean distance between the vectors
	"""

	# reshape the vectors for the euclidean distance calculation
	vector1_2d = numpy.array(vector1).reshape(1, -1)
	vector2_2d = numpy.array(vector2).reshape(1, -1)

	# calculate the euclidean distance while ignoring NaN entries
	euclidean_distance = nan_euclidean_distances(vector1_2d, vector2_2d)

	return euclidean_distance


def get_user_ratings_vector(user_id: int, movie_ids: list[int]):
	"""
	Gets a sparse vector of a user's ratings for a list of movies.

	:param user_id: id of the user the vector should be gotten of
	:param movie_ids: list of the ids of the movies the user's ratings should be added to the vector of
	:return: user_rating_vector - list of the user's ratings (or NaN) corresponding to the movies
	"""

	# get all MovieRating entries corresponding to the user
	user_ratings = MovieRating.query.filter(MovieRating.user_id == user_id, MovieRating.ignored == 0).order_by(
		MovieRating.movie_id).all()
	rated_movies_ids = [m.movie_id for m in user_ratings]
	user_movie_ratings = [m.rating for m in user_ratings]

	user_rating_vector = []
	# go through each movie
	for movie in movie_ids:
		# if there is a rating by the user for that movie, append the rating to the vector
		if movie in rated_movies_ids:
			user_rating_vector.append(user_movie_ratings[rated_movies_ids.index(movie)])
		# if there is no rating, append NaN instead
		else:
			user_rating_vector.append(math.nan)

	return user_rating_vector


def get_similar_users(max_distance: int):
	"""
	Gets users for which the euclidean distance of the rating vector and the current user's rating vector is at most the
	given value.

	:param max_distance: the maximum distance between the rating vectors of similar users and the current user that is
			allowed
	:return: exact_matches - users for which the distance between the rating vector and the current user's rating
			vector is 0,
			most_similar_users - remaining users for which the distance is at most max_distance
	"""

	# get the ids of all movies there are ratings of and all user ids
	global all_movie_ids_rated, all_user_ids
	try:
		all_movie_ids_rated
	except NameError:
		all_movie_ids_rated = None
	if all_movie_ids_rated is None:
		all_movie_ids_rated = get_all_rated_movies_ids()
	try:
		all_user_ids
	except NameError:
		all_user_ids = None
	if all_user_ids is None or current_user.id not in all_user_ids:
		_, all_user_ids = get_all_movies_and_users_ids()

	# create a matrix of the user rating vectors
	user_movie_matrix = []
	# get the user rating vectors for each user
	for user in all_user_ids:
		user_movie_matrix.append(get_user_ratings_vector(user, all_movie_ids_rated))

	# calculate the similarity between all users and the current user
	user_distances = []
	# go through all users and ignore the current user
	for user in all_user_ids:
		if user != current_user.id:
			# calculate the euclidean distance between the user's and the current user's rating vectors
			distance = calculate_euclidean_distance_between_vectors(
				user_movie_matrix[all_user_ids.index(current_user.id)],
				user_movie_matrix[all_user_ids.index(user)]).flatten().flatten()[0]
			# if the distance is not NaN save the distance in a list
			if not math.isnan(distance):
				user_distances.append([user, distance])

	# sort the distances in an increasing manner
	user_similarities_sorted = sorted(user_distances, key=lambda x: x[1], reverse=False)

	# get the exact matches (i.e. distance is 0) and the most similar users (i.e. 0 < distance <= max_distance)
	most_similar_users = []
	exact_matches = []
	for user in user_similarities_sorted:
		if user[1] == 0.0:
			exact_matches.append(user[0])
		elif user[1] <= max_distance:
			most_similar_users.append(user[0])

	# print("exact matches:", exact_matches)
	# print("similar users:", most_similar_users)

	return exact_matches, most_similar_users


def calculate_user_based_scores(min_rating_for_rec: float):
	"""
	Calculates the user_based_score attribute of UserMovieRecommendationScores corresponding to the current user. The
	score depends on whether the corresponding movie was liked by exact matches or most similar users of the current
	user that are determined by get_similar_users(max_distance).

	:param min_rating_for_rec: minimum rating exact matches/similar users need to have given a movie so that it is
			deemed as liked and considered for the recommendation for the current user
	"""

	# get a list of the ids of all movies the current user rated, excluding those they ignored
	movies_already_rated = MovieRating.query.filter(MovieRating.user_id == current_user.id,
	                                                MovieRating.ignored == 0).all()
	movies_already_rated_ids = [m.movie_id for m in movies_already_rated]
	# get a list of the ids of all movies the current user ignored
	ignored_movies = MovieRating.query.filter(MovieRating.user_id == current_user.id,
	                                          MovieRating.ignored == 1).all()
	ignored_movies_ids = [m.movie_id for m in ignored_movies]

	# print("get similar users")
	# get the ids of similar users and the euclidean distance between their rating vector and the current user's
	# rating vector
	exact_matches, most_similar_users_ids = get_similar_users(max_distance=30)

	# print("get movies from exact matches")
	# get the ids of all movies that exact matches liked, excluding those that the current user rated or ignored
	unrated_movies_exact_matches_liked = MovieRating.query.filter(
		MovieRating.user_id.in_(exact_matches),
		MovieRating.movie_id.not_in(movies_already_rated_ids),
		MovieRating.ignored == 0,
		MovieRating.rating >= min_rating_for_rec
		).all()
	unrated_movies_exact_matches_liked_ids = [m.movie_id for m in unrated_movies_exact_matches_liked]

	# print("update movie score for these movies to 1.0")
	# update the user based score attribute of these movies to 1.0
	(db.session.query(UserMovieRecommendationScores).filter(
		UserMovieRecommendationScores.user_id == current_user.id,
		UserMovieRecommendationScores.movie_id.in_(unrated_movies_exact_matches_liked_ids)
		).update({'user_based_score': 1.0}))
	db.session.commit()

	# print("get movies from similar users")
	# get the ids of all movies that similar users liked, excluding those that the current user rated or ignored
	unrated_movies_similar_users_liked = MovieRating.query.filter(
		MovieRating.user_id.in_(most_similar_users_ids),
		MovieRating.movie_id.not_in(movies_already_rated_ids),
		MovieRating.ignored == 0,
		MovieRating.rating >= min_rating_for_rec
		).all()
	unrated_movies_similar_users_liked_ids = [m.movie_id for m in unrated_movies_similar_users_liked]

	# print("update movie score for these movies to 0.5")
	# update the user based score attribute of these movies to 0.75
	(db.session.query(UserMovieRecommendationScores).filter(
		UserMovieRecommendationScores.user_id == current_user.id,
		UserMovieRecommendationScores.movie_id.in_(unrated_movies_similar_users_liked_ids),
		UserMovieRecommendationScores.movie_id.not_in(unrated_movies_exact_matches_liked_ids)
		).update({'user_based_score': 0.75}))
	db.session.commit()

	# print("reset all movies rated by the user to 0.0")
	# update the user based score attribute of all ignored and rated movies to 0.0
	all_rated_movies_by_user, _ = get_all_rated_movies_by_current_user()
	all_rated_movies_by_user_ids = [m.id for m in all_rated_movies_by_user]
	(db.session.query(UserMovieRecommendationScores).filter(
		UserMovieRecommendationScores.user_id == current_user.id,
		or_(UserMovieRecommendationScores.movie_id.in_(all_rated_movies_by_user_ids),
		    UserMovieRecommendationScores.movie_id.in_(ignored_movies_ids))
		).update({'user_based_score': 0.0}))
	db.session.commit()


def get_user_based_recommendations(amount_of_results: int):
	"""
	Gets a set amount of movie recommendations based on the user based score attribute in
	UserMovieRecommendationsScores.

	:param amount_of_results: amount of results that should be returned
	:return: user_based_recommendations - list of Movie objects of the recommended movies
	"""

	# print("get user-based recommendations by filtering the database")
	# sort the UserMovieRecommendationScores entries corresponding to the current user by the user based score attribute
	# in a descending manner and get the first amount_of_results entries and the corresponding movie ids
	user_based_recommendations_ids = UserMovieRecommendationScores.query.filter(
		UserMovieRecommendationScores.user_id == current_user.id
		).order_by(UserMovieRecommendationScores.user_based_score.desc()).limit(amount_of_results).all()

	user_based_recommendations_ids = [m.movie_id for m in user_based_recommendations_ids]

	id_ordering = case(
		{_id: index for index, _id in enumerate(user_based_recommendations_ids)},
		value=Movie.id
		)

	# print("get the corresponding Movie objects")
	# get the corresponding Movie objects ordered by the user based score attribute
	user_based_recommendations = (Movie.query.filter(Movie.id.in_(user_based_recommendations_ids))
	                              .order_by(id_ordering).all())

	return user_based_recommendations
# endregion


# region item-based
def calculate_item_based_scores(genre_ratios: dict[any, list], decade_ratios: dict[any, list]):
	"""
	Calculates the item_based_score attribute of UserMovieRecommendationScores corresponding to the current user. The
	score depends on how well the genres and the release year of the corresponding movie fit the current user's
	preferences

	:param genre_ratios: dictionary with genres as keys and a list of the "liked" and the "disliked" ratio as values
	:param decade_ratios: dictionary with decades as keys and a list of the "liked" and the "disliked" ratio as values
	"""

	global all_movie_ids
	try:
		all_movie_ids
	except NameError:
		all_movie_ids = None
	if all_movie_ids is None:
		all_movie_ids, _ = get_all_movies_and_users_ids()

	# get a list of the ids of all movies the current user rated, excluding those they ignored
	movies_already_rated = MovieRating.query.filter(MovieRating.user_id == current_user.id,
	                                                MovieRating.ignored == 0).all()
	movies_already_rated_ids = [m.movie_id for m in movies_already_rated]
	# get a list of the ids of all movies the current user ignored
	ignored_movies = MovieRating.query.filter(MovieRating.user_id == current_user.id,
	                                          MovieRating.ignored == 1).all()
	ignored_movies_ids = [m.movie_id for m in ignored_movies]
	# print("GENRES")
	# region genres
	# count = 0
	new_scores = {}
	# go through all movies
	for movie in all_movie_ids:
		# count += 1
		# if count % 1000 == 0:
		# print("loop count:", count)
		# if count == len(all_movie_ids):
		# print("last loop")
		# if the current user ignored or rated the movie, set the score to 0.0
		if movie in ignored_movies_ids or movie in movies_already_rated_ids:
			score = 0.0
		else:
			# get all genres of the movie
			movie_genres = get_movie_genres(movie)
			amount_of_genres = len(movie_genres)
			score = 0.0
			# go through each genre
			for genre in movie_genres:
				# if no genre is listed, add a small score for recommendation to not exclude it
				if genre is None:
					score = 0.25
					break
				# increase the score by a proportional factor based on the current user's genre ratios
				# e.g. if the user liked 40% of the Comedy movies they rated and disliked 60% of them,
				# and the movie has 4 genres in total, the factor would be: (1/4) * max(0, (1 * 0.4 + (-1) * 0.6))
				# = (1/4) * max(0, (-0.2)) = 0
				else:
					score += (1 / amount_of_genres) * (1 * genre_ratios[genre][0] + (-1) * genre_ratios[genre][1])
		# append the score to the dictionary
		new_scores[movie] = round(score, 2)
	# endregion

	# print("DECADES")
	# region release years
	# count = 0
	# go through all movies
	for movie in all_movie_ids:
		# count += 1
		# if count % 1000 == 0:
		# print("loop count:", count)
		# if count == len(all_movie_ids):
		# print("last loop")
		# if the current user ignored or rated the movie, set the score to 0.0
		if movie in ignored_movies_ids or movie in movies_already_rated_ids:
			score = 0.0
		else:
			# get the release year of the movie
			year = Movie.query.filter(Movie.id == movie).first().release_year
			if year is not None:
				# get the corresponding decade
				decade = math.floor(year / 10) * 10
				# calculate the score based on the current user's decade ratios
				score = 1 * (1 * decade_ratios[decade][0] + (-1) * decade_ratios[decade][1])
			else:
				# if movie does not have a release year, add a small score for recommendation to not exclude it
				score = 0.25
		# if the genre-based movie score + the calculated decade-based score is not between 0.0 and 1.0, cast it
		if new_scores[movie] + score > 1.0:
			new_scores[movie] = 1.0
		elif new_scores[movie] + score < 0.0:
			new_scores[movie] = 0.0
		# else append the sum to the dictionary
		else:
			new_scores[movie] = round((new_scores[movie] + score), 2)
	# create a temporary table
	try:
		temp = Table("temp", db.metadata,
		             Column("movie_id", db.Integer),
		             Column("item_based_score", db.Float),
		             extend_existing=True
		             )
	except exc.InvalidRequestError:
		temp = None
	if temp is None:
		temp = Table("temp", db.metadata,
		             Column("movie_id", db.Integer),
		             Column("item_based_score", db.Float),
		             extend_existing=True
		             )
	db.session.commit()
	temp.create(bind=db.session.get_bind())

	# insert the dictionary with the new scores
	db.session.execute(
		temp.insert().values([{"movie_id": k, "item_based_score": v} for k, v in new_scores.items()]))

	# update the UserMovieRecommendationScores entries that correspond the current user
	db.session.execute(UserMovieRecommendationScores.__table__.update().values(
		item_based_score=temp.c.item_based_score).where(and_(
		UserMovieRecommendationScores.__table__.c.movie_id == temp.c.movie_id,
		UserMovieRecommendationScores.__table__.c.user_id == current_user.id)))
	db.session.commit()

	# drop the temporary table
	temp.drop(bind=db.session.get_bind())


def get_item_based_recommendations(amount_of_results: int):
	"""
	Gets a set amount of movie recommendations based on the item based score attribute in
	UserMovieRecommendationsScores.

	:param amount_of_results: amount of results that should be returned
	:return: item_based_recommendations - list of Movie objects of the recommended movies
	"""

	# print("get item-based recommendations by filtering the database")
	# sort the UserMovieRecommendationScores entries corresponding to the current user by the item based score attribute
	# in a descending manner and get the first amount_of_results entries and the corresponding movie ids
	item_based_recommendations_ids = UserMovieRecommendationScores.query.filter(
		UserMovieRecommendationScores.user_id == current_user.id
		).order_by(UserMovieRecommendationScores.item_based_score.desc()).limit(amount_of_results).all()

	item_based_recommendations_ids = [m.movie_id for m in item_based_recommendations_ids]

	id_ordering = case(
		{_id: index for index, _id in enumerate(item_based_recommendations_ids)},
		value=Movie.id
		)

	# print("get the corresponding Movie objects")
	# get the corresponding Movie objects ordered by the item based score attribute
	item_based_recommendations = Movie.query.filter(
		Movie.id.in_(item_based_recommendations_ids),
		).order_by(id_ordering).all()

	return item_based_recommendations
# endregion


# region hybrid
def calculate_hybrid_scores():
	"""
	Calculates the total_recommendation_score attribute of UserMovieRecommendationScores corresponding to the current
	user. The score is a weighted sum of the survey-based, user-based, item-based and exploration-based score of a
	movie if the current user submitted the preference survey, or of the user-based, item-based and exploration-based
	score of a movie.
	"""

	# print("go through all movies to calculate weighted scores")
	# if there are survey entries by the current user, calculate the score based on the corresponding survey-based,
	# user-based, item-based and exploration-based score and update the entry
	if check_whether_there_are_survey_entries():
		# print("4-part calculation (including survey-based scores)")
		(db.session.query(UserMovieRecommendationScores).filter(
			UserMovieRecommendationScores.user_id == current_user.id).update(
			{'total_recommendation_score': func.round(0.25 * UserMovieRecommendationScores.survey_based_score +
			                                          0.15 * UserMovieRecommendationScores.exploration_based_score +
			                                          0.3 * UserMovieRecommendationScores.user_based_score +
			                                          0.3 * UserMovieRecommendationScores.item_based_score, 2)}))
	# if there are no survey entries by the current user, calculate the score based on the corresponding user-based,
	# item-based and exploration-based score instead and update the entry
	else:
		# print("3-part calculation (without survey-based scores)")
		(db.session.query(UserMovieRecommendationScores).filter(
			UserMovieRecommendationScores.user_id == current_user.id).update(
			{'total_recommendation_score': func.round(0.2 * UserMovieRecommendationScores.exploration_based_score +
			                                          0.4 * UserMovieRecommendationScores.user_based_score +
			                                          0.4 * UserMovieRecommendationScores.item_based_score, 2)}))
	db.session.commit()


def get_hybrid_recommendations(amount_of_results):
	"""
	Gets a set amount of movie recommendations based on the total recommendation score attribute in
	UserMovieRecommendationsScores.

	:param amount_of_results: amount of results that should be returned
	:return: hybrid_recommendations = list of Movie objects of the recommended movies
	"""

	# get movies by score from the database
	# print("get hybrid recommendations by filtering the database")
	# sort the UserMovieRecommendationScores entries corresponding to the current user by the total recommendation score
	# attribute in a descending manner and get the first amount_of_results entries and the corresponding movie ids
	hybrid_recommendations_ids = UserMovieRecommendationScores.query.filter(
		UserMovieRecommendationScores.user_id == current_user.id
		).order_by(UserMovieRecommendationScores.total_recommendation_score.desc()).limit(amount_of_results).all()

	hybrid_recommendations_ids = [m.movie_id for m in hybrid_recommendations_ids]

	id_ordering = case(
		{_id: index for index, _id in enumerate(hybrid_recommendations_ids)},
		value=Movie.id
		)

	# print("get corresponding Movie objects")
	# get the corresponding Movie objects ordered by the total recommendation score attribute
	hybrid_recommendations = Movie.query.filter(
		Movie.id.in_(hybrid_recommendations_ids),
		).order_by(id_ordering).all()

	return hybrid_recommendations
# endregion


# region ignore movie
def ignore_movie_for_recommendations(movie_id: int):
	"""
	Sets a movie to ignored by updating the MovieRating entry, deleting the rating and updating the	average movie rating
	if the current user rated the movie already, and updating the MovieWatchList entry.

	:param movie_id: id of the movie to be ignored
	"""

	# set movie to ignored in MovieRating
	add_or_update_ignored_status(movie_id, True)

	# if movie was rated by the current user, delete movie features from genre and decade preferences so that they are
	# no longer included in the recommendations and update the average rating of the movie
	rating_entry = MovieRating.query.filter(
		MovieRating.movie_id == movie_id,
		MovieRating.user_id == current_user.id
		).first()

	if rating_entry.rating is not None:
		delete_movie_features_from_preferences(movie_id, rating_entry.rating)
		update_average_movie_rating(movie_id, rating_entry.rating, method="delete")

	# set movie to ignored in MovieWatchList if movie is on the watchlist
	watchlist_entry = MovieWatchList.query.filter(MovieWatchList.movie_id == movie_id,
	                                              MovieWatchList.user_id == current_user.id).first()
	if watchlist_entry:
		setattr(watchlist_entry, 'ignored', True)
		db.session.commit()


def delete_movie_features_from_preferences(movie_id: int, movie_rating: float):
	"""
	Deletes the entries in UserGenrePreferences and UserDecadePreferences that are associated with a movie.

	:param movie_id: id of the movie the features should be deleted from
	:param movie_rating: the rating of the movie by the current user to access the correct preference entries
	"""

	# get all movie genres of the movie
	genres = get_movie_genres(movie_id)
	for genre in genres:
		if genre is None:
			continue
		# get the respective row in UserGenrePreferences for the genre
		row = UserGenrePreferences.query.filter(UserGenrePreferences.user_id == current_user.id,
		                                        UserGenrePreferences.genre == genre).first()
		# decrease the amount of ratings for the genre by 1
		setattr(row, 'amount_of_ratings', UserGenrePreferences.amount_of_ratings - 1)
		db.session.commit()
		# if movie was liked, decrease the amount of liked movies
		if movie_rating > 3.5:
			setattr(row, 'amount_of_likes', UserGenrePreferences.amount_of_likes - 1)
			db.session.commit()
		# if movie was disliked, decrease the amount of disliked movies instead
		elif movie_rating < 2.5:
			setattr(row, 'amount_of_dislikes', UserGenrePreferences.amount_of_dislikes - 1)
			db.session.commit()

	# get the release year of the movie
	year = Movie.query.filter(Movie.id == movie_id).first().release_year
	if year is not None:
		# get the corresponding decade
		decade = math.floor(year / 10) * 10
		# get the respective row in UserDecadePreferences for the decade
		row = UserDecadePreferences.query.filter(UserDecadePreferences.user_id == current_user.id,
		                                         UserDecadePreferences.decade == decade).first()
		# decrease the amount of ratings by 1
		setattr(row, 'amount_of_ratings', UserDecadePreferences.amount_of_ratings - 1)
		db.session.commit()
		# if movie was liked, decrease the amount of liked movies
		if movie_rating > 3.5:
			setattr(row, 'amount_of_likes', UserDecadePreferences.amount_of_likes - 1)
			db.session.commit()
		# if the movie was disliked, decrease the amount of disliked movies instead
		elif movie_rating < 2.5:
			setattr(row, 'amount_of_dislikes', UserDecadePreferences.amount_of_dislikes - 1)
			db.session.commit()


def revoke_ignore_movie_for_recommendations(movie_id: int):
	"""
	Reverses ignore_movie_for_recommendations(movie_id).

	:param movie_id: id of the movie that should no longer be ignored
	"""

	# set movie to not ignored in MovieRating
	add_or_update_ignored_status(movie_id, False)

	# if movie was rated by the current user, add movie features from genre and decade preferences so that they are
	# included in the recommendations again and update the average rating of the movie
	rating_entry = MovieRating.query.filter(
		MovieRating.movie_id == movie_id,
		MovieRating.user_id == current_user.id
		).first()

	if rating_entry.rating is not None:
		add_or_update_user_preferences(movie_id, rating_entry.rating)
		update_average_movie_rating(movie_id, rating_entry.rating, method="add")

	# set movie to not ignored in MovieWatchList if movie is on the watchlist
	watchlist_entry = MovieWatchList.query.filter(MovieWatchList.movie_id == movie_id,
	                                              MovieWatchList.user_id == current_user.id).first()
	if watchlist_entry:
		setattr(watchlist_entry, 'ignored', False)
		db.session.commit()


def add_or_update_ignored_status(movie_id: int, ignored: bool):
	"""
	Adds a new MovieRating entry or updates an existing one with respect to the ignored column.

	:param movie_id: id of the movie the entry should be added or updated for
	:param ignored: truth value that the ignored attribute of the MovieRating entry should be set to
	"""

	# get the current time if movie is ignored
	if ignored:
		current_GMT = time.gmtime()
		timestamp = calendar.timegm(current_GMT)
	# if movie is "un"-ignored, set the timestamp to NaN
	else:
		timestamp = math.nan

	# try to get the MovieRating entry
	existent_rating = MovieRating.query.filter(
		MovieRating.user_id == current_user.id,
		MovieRating.movie_id == movie_id,
		).first()
	# if there is an entry, update the ignored value
	if existent_rating:
		setattr(existent_rating, 'ignored', ignored)
		setattr(existent_rating, 'time_ignored', timestamp)
		db.session.commit()
	# if there is no entry, add a new one with rating set to NaN
	else:
		new_rating = MovieRating(user_id=current_user.id, movie_id=movie_id, rating=math.nan,
		                         time_rated=math.nan, ignored=ignored, time_ignored=timestamp)
		db.session.add(new_rating)
		db.session.commit()
# endregion


# region rate movie
def add_new_rating_or_update(movie_id, rating):
	"""
	Adds a new MovieRating entry or updates an existing one.

	:param movie_id: id of the movie for which the entry should be added or updated
	:param rating: corresponding rating that should be added or updated
	"""

	# get the current time
	current_GMT = time.gmtime()
	timestamp = calendar.timegm(current_GMT)

	# try to get the MovieRating entry
	existent_rating = MovieRating.query.filter(
		MovieRating.user_id == current_user.id,
		MovieRating.movie_id == movie_id,
		).first()
	# if there is an entry, update the rating value and the time rated attribute
	if existent_rating:
		setattr(existent_rating, 'rating', rating)
		setattr(existent_rating, 'time_rated', timestamp)
		db.session.commit()
	# if there is no entry, add a new one with ignored set to False (if there is no entry, the movie cannot be set to
	# ignored as there would be an entry then
	else:
		new_rating = MovieRating(user_id=current_user.id, movie_id=movie_id, rating=rating, time_rated=timestamp,
		                         ignored=False, time_ignored=math.nan)
		db.session.add(new_rating)
		db.session.commit()
# endregion


def update_scores_of_ignored_or_rated_movie(movie_id: int):
	"""
	Sets all score attributes in UserMovieRecommendationScores of a movie to 0.0 for the current user.

	:param movie_id: id of the movie that the scores should be updated for
	"""

	# update the database entries
	(db.session.query(UserMovieRecommendationScores).filter(
		UserMovieRecommendationScores.user_id == current_user.id,
		UserMovieRecommendationScores.movie_id == movie_id
		).update(
		{'survey_based_score': 0.0,
		 'user_based_score': 0.0,
		 'item_based_score': 0.0,
		 'exploration_based_score': 0.0,
		 'total_recommendation_score': 0.0}))
	db.session.commit()


def update_data_after_rating(movie_id: int, rating: float):
	"""
	Updates all necessary data after a user rated a movie.

	:param movie_id: id of the movie that was rated
	:param rating: rating of the movie
	"""

	global all_movie_ids_rated
	# get the ids of all movies that were rated
	try:
		all_movie_ids_rated
	except NameError:
		all_movie_ids_rated = None
	if all_movie_ids_rated is None:
		all_movie_ids_rated = get_all_rated_movies_ids()

	# update all rated movies if movie_id not in all_movie_ids_rated
	if movie_id not in all_movie_ids_rated:
		all_movie_ids_rated = get_all_rated_movies_ids()

	# update the average movie ratings
	update_average_movie_rating(movie_id, rating, "add")

	# update the current user's rating distribution for the genres and release year of the movie
	add_or_update_user_preferences(movie_id, float(rating))

	# set the movie scores of the movie to 0
	update_scores_of_ignored_or_rated_movie(movie_id)

	# update the MovieWatchList entry if the current user added the movie to their watchlist
	watchlist_entry = MovieWatchList.query.filter(MovieWatchList.movie_id == movie_id,
	                                              MovieWatchList.user_id == current_user.id).first()
	if watchlist_entry:
		setattr(watchlist_entry, 'rated', True)


def update_average_movie_rating(movie_id: int, rating: float, method: str = "add"):
	"""
	Recalculates the average rating of a movie based on a rating and updates the Movie entry for the corresponding
	movie.

	:param movie_id: id of the movie the average rating should be updated for
	:param rating: rating of the movie by the current user
	:param method: indicates whether the rating should be added or deleted from the average rating
	"""

	# if the method is add, calculate the new average movie rating by adding the rating
	if method == "add":
		# if the amount of ratings is None or 0, add the rating as the average rating and increase the amount of
		# ratings by 1
		if (Movie.query.filter(Movie.id == movie_id).first().amount_of_ratings is None or
				Movie.query.filter(Movie.id == movie_id).first().amount_of_ratings == 0):
			db.session.query(Movie).filter(Movie.id == movie_id).update({
				'average_rating': func.round(rating, 2),
				'amount_of_ratings': 1
				})
			db.session.commit()
		# else, recalculate the new average movie rating and increase the amount of ratings by 1
		else:
			db.session.query(Movie).filter(Movie.id == movie_id).update({
				'average_rating': func.round(
					(((Movie.average_rating * Movie.amount_of_ratings) + rating) / (Movie.amount_of_ratings + 1)), 2),
				'amount_of_ratings': Movie.amount_of_ratings + 1
				})
		db.session.commit()
	# if the method is delete, calculate the new average movie rating by deleting the rating from it instead and
	# decrease the amount of ratings by 1
	elif method == "delete":
		(db.session.query(Movie).filter(Movie.id == movie_id)
		 ).update({'average_rating': func.round(
			((Movie.average_rating * Movie.amount_of_ratings) - rating) / (Movie.amount_of_ratings - 1), 2),
			'amount_of_ratings': Movie.amount_of_ratings - 1})
		db.session.commit()


# region watchlist
def add_movie_to_watchlist(movie_id: int):
	"""
	Adds an entry for a movie to MovieWatchList that corresponds to the current user.

	:param movie_id: id of the movie that a MovieWatchList entry should be added for
	"""

	# get the MovieRating entry for the movie and current user to be able to set the rated and ignored attributes in
	# MovieWatchList
	rating = MovieRating.query.filter(
		MovieRating.user_id == current_user.id,
		MovieRating.movie_id == movie_id).first()

	# get the current time
	current_GMT = time.gmtime()
	timestamp = calendar.timegm(current_GMT)

	# check if movie is already on watchlist (should not be possible)
	row = MovieWatchList.query.filter(
		MovieWatchList.movie_id == movie_id,
		MovieWatchList.user_id == current_user.id).first()
	# if yes, update the timestamp
	if row:
		setattr(row, 'time_added', timestamp)
		db.session.commit()
	# if not, add a new entry for the movie for the user
	else:
		new_watchlist_entry = MovieWatchList(movie_id=movie_id, user_id=current_user.id, time_added=timestamp,
		                                     rated=True if rating else False,
		                                     ignored=rating.ignored if rating else False)
		db.session.add(new_watchlist_entry)
		db.session.commit()


def delete_movie_from_watchlist(movie_id):
	"""
	Deletes the MovieWatchList entry of a movie that corresponds to the current user.

	:param movie_id: id of the movie the MovieWatchList entry should be deleted of
	"""

	# get the MovieWatchList entry and delete it
	MovieWatchList.query.filter(
		MovieWatchList.movie_id == movie_id,
		MovieWatchList.user_id == current_user.id).delete()
	db.session.commit()
# endregion
