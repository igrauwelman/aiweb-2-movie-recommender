import re
from thefuzz import fuzz

from sqlalchemy import case
from models import db, Movie, Tags


def get_all_movie_titles_without_release_years():
	"""
	Gets all movie titles without the release years.
	:return: movies - list of the movie ids and the corresponding movie title without the release year
	"""

	# get all movie titles
	movie_ids_and_titles = db.session.query(Movie.id, Movie.title).order_by(Movie.title).all()

	movies = []
	# go through the movies and edit the movie title before appending the id and the title to the list
	for id_and_title in movie_ids_and_titles:
		parenthesis_index = id_and_title.title[::-1].find("(")
		movies.append([id_and_title.id, id_and_title.title[::-1][parenthesis_index+1:][::-1]])

	return movies


def preprocess_string(string: str):
	"""
	Preprocesses a string by converting it to lowercase and removing punctuation.

	:param string: string to be preprocessed
	:return: string_preprocessed - preprocessed string
	"""

	# convert to lowercase
	string_lowercase = string.lower()
	# remove punctuation
	string_preprocessed = re.sub(r'[^a-zäöüß0-9+ ]', '', string_lowercase)

	return string_preprocessed


def find_movies_by_query(search_query: str, min_similarity: int):
	"""
	Finds movies that the title and/or the tags match the search_query of.

	:param search_query: search term
	:param min_similarity: minimum similarity that needs to be reached to be deemed as a match
	:return: resulting_title_matches, resulting_tag_matches - lists of Movie objects corresponding to the matches
	"""

	# print("preprocess search query")
	# preprocess the search query
	query_preprocessed = preprocess_string(search_query)
	# print("query preprocessed:", query_preprocessed)

	# print("get all movie titles without release years")
	# get the movie titles without the release years
	movies = get_all_movie_titles_without_release_years()
	# print("preprocess the titles")
	# preprocess the titles
	movies_preprocessed = [[movie[0], preprocess_string(movie[1])] for movie in movies]

	similarities_titles = []
	similarities_tags = []
	# print("go through each preprocessed movie to find matches")
	# count = 0
	# go through all movies
	for movie in movies_preprocessed:
		# count += 1
		# if count % 1000 == 0:
		#	print(count, "loops done")
		# if count == len(movies_preprocessed):
		#	print("last loop")
		# get amount of ratings

		# get the amount of ratings of the movie
		amount_of_ratings = Movie.query.filter(Movie.id == movie[0]).first().amount_of_ratings

		# get the movie's tags
		movie_tags = Tags.query.filter(Tags.movie_id == movie[0]).all()
		tags = [m.tag for m in movie_tags]

		# get exact matches first
		exact_match_title = False  # title has to match query perfectly for this to be True
		for word in query_preprocessed.split():
			if word in movie[1].split():
				exact_match_title = True
			else:
				exact_match_title = False
				break
		# set the similarity to either 0 or 101, depending on whether there was an exact match; value of 101 ensures
		# that the exact matches are shown first if there are also similar matches with a similarity of 100
		exact_similarity_title = int(exact_match_title) * 101

		# a tag has to match the query at least in parts exactly for this to be True
		# e.g. query = "Anime movie", tag = "Anime" should be an exact match
		# but tags "time travel" and "time-travel" should also count as an exact match for query "timetravel"
		amount_of_exact_matches = 0
		tags_left_to_check_for_partial_match = []
		for tag in tags:
			tag_preprocessed = preprocess_string(tag)
			if fuzz.token_sort_ratio(tag_preprocessed, query_preprocessed) >= 90:
				amount_of_exact_matches += 1
			else:
				tags_left_to_check_for_partial_match.append(tag_preprocessed)
		# set the similarity depending on how many exact matches there are; value of 101 ensures
		# that the exact matches are shown first if there are also similar matches with a similarity of 100
		exact_similarity_tags = amount_of_exact_matches * 101

		# get fuzzy similarity between query and movie title
		similarity_title = fuzz.partial_ratio(query_preprocessed, movie[1])
		similarities_titles.append([movie[0], movie[1], similarity_title + exact_similarity_title,
									amount_of_ratings if amount_of_ratings is not None else 0])

		# get fuzzy similarity between query and the remainder of the tags
		similarity = 0
		for tag in tags_left_to_check_for_partial_match:
			# check if the query is made up of more than one word
			if " " in query_preprocessed:
				query_terms = [term for term in query_preprocessed.split(" ") if len(term) > 3]
			else:
				query_terms = [query_preprocessed]
			# check if the tag is made up of more than one word and check the parts for matches instead
			if " " in tag:
				words = [word for word in tag.split(" ") if len(word) > 3]
				# if one of the words is an exact match with (part of) the query, add to the similarity score
				for word in words:
					if word in query_terms:
						similarity += min_similarity

		similarities_tags.append(
			[movie[0], similarity + exact_similarity_tags if similarity + exact_similarity_tags <= 101 else 101,
			 amount_of_ratings if amount_of_ratings is not None else 0])

	# print("sort similarities of titles and tags")
	# print("title based:", [similarity for similarity in similarities_titles if similarity[2] >= min_similarity])
	# sort similarities in a descending order, first by the similarity, then by the amount of ratings (= popularity)
	similarities_titles_sorted = sorted(similarities_titles, key=lambda x: (x[2], x[3]), reverse=True)
	similarities_tags_sorted = sorted(similarities_tags, key=lambda x: (x[1], x[2]), reverse=True)
	# print("filter for best matches")
	# keep movies that have a similarity score of at least min_similarity as matches
	title_matches_ids = [movie[0] for movie in similarities_titles_sorted if movie[2] >= min_similarity]
	tag_matches_ids = [movie[0] for movie in similarities_tags_sorted if movie[1] > 0]

	# print("get movie objects of title matches")
	# if there are title matches, get the corresponding Movie objects
	if title_matches_ids:
		id_ordering_titles = case(
			{_id: index for index, _id in enumerate(title_matches_ids)},
			value=Movie.id
			)
		resulting_title_matches = Movie.query.filter(Movie.id.in_(title_matches_ids)).order_by(id_ordering_titles).all()
	else:
		resulting_title_matches = []

	# print("get movie objects of tag matches")
	# if there are tag matches, get the corresponding Movie objects
	if tag_matches_ids:
		id_ordering_tags = case(
			{_id: index for index, _id in enumerate(tag_matches_ids)},
			value=Movie.id
			)
		resulting_tag_matches = Movie.query.filter(Movie.id.in_(tag_matches_ids)).order_by(id_ordering_tags).all()
	else:
		resulting_tag_matches = []

	return resulting_title_matches, resulting_tag_matches
