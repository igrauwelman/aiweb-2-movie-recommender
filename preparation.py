from flask_login import current_user
from sqlalchemy import Table, Column, exc, func, and_
from thefuzz import fuzz
import math

from get_data import get_all_movies_and_users_ids, get_all_movie_genres
from models import UserMovieRecommendationScores, db, Movie, MovieRating, Tags

global all_movie_ids


def preprocess_tags():
	"""
	Preprocesses the movie tags by removing the genres part of the movie genres and merging similar tags.
	"""

	# print("preprocess tags")
	global all_movie_ids
	try:
		all_movie_ids
	except NameError:
		all_movie_ids = None
	if all_movie_ids is None:
		all_movie_ids, _ = get_all_movies_and_users_ids()

	# get all movie genres
	all_genres = get_all_movie_genres()
	# capitalize them to be able to compare them to the tags
	all_genres = [genre.upper() for genre in all_genres]
	# go through all movies (in a reversed order to be able to safely delete entries without index shifting)
	for movie in all_movie_ids[::-1]:
		# get all tags of the movie
		movie_tags = Tags.query.filter(Tags.movie_id == movie).all()
		tags = [tags.tag for tags in movie_tags]
		# if there are tags, preprocess them
		if tags:
			# step 1: remove the genres
			preprocessed_tags_without_genres = []
			# go through each tag and delete the entries corresponding to a genre
			for tag in tags:
				if tag in all_genres:
					Tags.query.filter(
						Tags.movie_id == movie,
						Tags.tag == tag
						).delete()
					db.session.commit()
				# append the tags not corresponding to a genre to the list
				else:
					preprocessed_tags_without_genres.append(tag)
			# step 2: merge very similar tags into one
			# go through the remaining tags to merge similar ones
			for tag in preprocessed_tags_without_genres:
				for other_tag in preprocessed_tags_without_genres:
					if other_tag == tag:
						break
					similarity = fuzz.partial_ratio(tag, other_tag)
					if similarity >= 85:
						Tags.query.filter(
							Tags.movie_id == movie,
							Tags.tag == other_tag
							).delete()
						db.session.commit()
# print("done (tag preprocessing)")


def get_and_save_amount_of_ratings_and_average_ratings():
	"""
	Get the amount of ratings and the average rating of all movies and add them to the corresponding Movie entries.
	"""

	# print("get amount of ratings and average ratings")
	# calculate the amount of ratings and the average ratings based on the MovieRating entries
	amounts_and_averages = (db.session.query(MovieRating.movie_id,
	                                         func.count(MovieRating.rating).label('amount_of_ratings'),
	                                         func.avg(MovieRating.rating).label('average_rating'))
	                        .group_by(MovieRating.movie_id).all())

	# save the values to a dictionary
	data = {}
	for m in amounts_and_averages:
		data[m[0]] = [m[1] if m[1] else 0, round(m[2], 2) if m[2] else math.nan]
	# print("save amount of ratings and average ratings of the movies to the database")

	# create a temporary table
	try:
		t = Table("t", db.metadata,
		          Column("movie_id", db.Integer),
		          Column("amount_of_ratings", db.Integer),
		          Column("average_rating", db.Float),
		          extend_existing=True
		          )
	except exc.InvalidRequestError:
		t = None
	if t is None:
		t = Table("t", db.metadata,
		          Column("movie_id", db.Integer),
		          Column("amount_of_ratings", db.Integer),
		          Column("average_rating", db.Float),
		          extend_existing=True
		          )
	db.session.commit()
	t.create(bind=db.session.get_bind())

	# insert the values
	db.session.execute(
		t.insert().values(
			[{"movie_id": k, "amount_of_ratings": v[0], "average_rating": v[1]} for k, v in data.items()]))

	# update the Movie entries
	db.session.execute(Movie.__table__.update().values(
		{'amount_of_ratings': t.c.amount_of_ratings, 'average_rating': t.c.average_rating}).where(and_(
		Movie.__table__.c.id == t.c.movie_id)))
	db.session.commit()

	# drop the temporary table
	t.drop(bind=db.session.get_bind())


def initialize_user_movie_scores():
	"""
	Initializes the entries in UserMovieRecommendationScores for the current user.
	"""

	# get a list of all movie ids
	global all_movie_ids
	try:
		all_movie_ids
	except NameError:
		all_movie_ids = None
	if all_movie_ids is None:
		all_movie_ids, _ = get_all_movies_and_users_ids()

	# generate a new entry for each movie and add it to a list of all new entries
	entries = []
	for movie in all_movie_ids:
		new_entry = UserMovieRecommendationScores(user_id=current_user.id, movie_id=movie, survey_based_score=0,
		                                          user_based_score=0, item_based_score=0, exploration_based_score=0,
		                                          total_recommendation_score=0)
		entries.append(new_entry)
	# add all entries to the database
	db.session.add_all(entries)
	db.session.commit()
