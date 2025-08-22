import csv
import math

import sqlalchemy
from sqlalchemy.exc import IntegrityError
from models import Movie, MovieGenre, MovieRating, Links, Tags, User
import random
import pandas as pd
import re

# list of possible articles in the dataset
articles = ["The", "A", "An", "El", "La", "Los", "Las", "Un", "Una", "Unos", "Unas", "Der", "Die", "Das", "Ein", "Eine",
            "Le", "Les", "Une", "Des", "L", "Il", "Lo", "Uno", "I", "Gli", "Det"]


def get_clean_movie_title(movie_title: str):
    """
    Reorders a movie title from the MovieLens dataset if it has an article (e.g. "American President, The (1995)" gets
    reordered to "The American President (1995)".

    :param movie_title: title to be reordered
    :return: reordered_movie_title if there are articles in the title - the reordered title,
            movie_title if there are no articles in the title and thus no reordering is needed - the original title
    """

    reordered_constituents = []
    # variable for the index of the word containing the opening bracket "(" (is there is one in the title)
    opening_index = -1
    # check if the title includes a comma as this would make it likely that there is an article
    if "," in movie_title:
        # get a list of the single words of the title
        constituents = movie_title.split()
        # go through each word
        for i, c in enumerate(constituents):
            # if the word starts with an opening bracket, save the index of the word in the wordlist
            if c[0] == "(":
                opening_index = i
            # if the last char of the word is a comma, save the next word in the wordlist and preprocess it by
            # removing punctuation as it could be an article
            if c[len(c) - 1] == ",":
                potential_article = constituents[i + 1]
                potential_article_raw = re.sub(r'[^A-Za-zÄÖÜäöüß0-9+ ]', '', potential_article)
                # if the potential article is indeed an article, get the remainder of the wordlist to append it
                if potential_article_raw in articles:
                    # Example: "Important Title, The (Wichtige Titel, Der) (2024)"
                    remainder = constituents[i + 2:]  # "Wichtige Titel, Der) (2024)" / "(2024)"
                    # check if the article ends in a closing bracket, in which case the article needs to be moved to the
                    # start of the bracketed expression instead of to the beginning of the title
                    if ")" in potential_article:
                        # remove closing bracket from the article
                        potential_article = potential_article[:len(potential_article) - 1]  # "Der"
                        # get the words before the critical part (i.e. the words before the bracketed expression)
                        prev_words = (constituents[:opening_index] if not reordered_constituents else
                                      reordered_constituents[:opening_index])  # "The Important Title"
                        # remove opening bracket from the first word in the brackets
                        first_word_in_parenthesis = constituents[opening_index][1:]  # "Wichtige"
                        # if the first word is also the word before the article, reset to not double the word in the
                        # result
                        if constituents[opening_index + 1] == ''.join([potential_article, ")"]):
                            first_word_in_parenthesis = ""
                        # add the closing bracket to the last word before the comma/the article)
                        word_before_prev_comma = ''.join([constituents[i][:len(constituents[i]) - 1], ")"])  # "Titel)"
                        # if the word is also the first one in the brackets, remove the opening bracket
                        if word_before_prev_comma[0] == "(":
                            word_before_prev_comma = word_before_prev_comma[1:]
                            words_in_between = [""]
                        # if not, and it is also not the one after the first one in the brackets, get the words in
                        # between
                        elif not constituents[opening_index + 1] == constituents[i]:
                            words_in_between = constituents[opening_index + 1:i]
                        else:
                            words_in_between = [""]
                        # fill the list of reordered constituents by concatenating the parts
                        reordered_constituents = (prev_words + [''.join(["(", potential_article])] + [
                            first_word_in_parenthesis] + words_in_between + [word_before_prev_comma] + remainder)
                        # remove potential "empty" elements
                        reordered_constituents = [c for c in reordered_constituents if len(c) > 0]
                    # if instead of a bracket there is a colon in the article, do the same but with a non-bracketed
                    # expression instead
                    elif ":" in potential_article:
                        potential_article = potential_article[:len(potential_article) - 1]
                        prev_part = reordered_constituents[:i] if reordered_constituents else [""]
                        prev_words = constituents[:i] if not reordered_constituents else reordered_constituents[:i]
                        word_before_prev_comma = constituents[i][:len(constituents[i]) - 1] + ":"
                        reordered_constituents = (prev_part + [potential_article] + prev_words +
                            [word_before_prev_comma] + remainder)
                        reordered_constituents = [c for c in reordered_constituents if len(c) > 0]
                    else:
                        # get the words before the critical part
                        prev_part = reordered_constituents[:i] if reordered_constituents else [""]
                        prev_words = (constituents[:i] if not reordered_constituents else
                                      reordered_constituents[:i])  # "Important"
                        word_before_prev_comma = constituents[i][:len(constituents[i]) - 1]  # "Title"
                        reordered_constituents = (prev_part + [potential_article] + prev_words +
                            [word_before_prev_comma] + remainder)
                        reordered_constituents = [c for c in reordered_constituents if len(c) > 0]
    # if the list with the reordered constituents is not empty, reordering was necessary
    if reordered_constituents:
        # convert the list to a string of the reordered title and return it
        reordered_movie_title = ' '.join(reordered_constituents)
        return reordered_movie_title
    # if the list is empty, no reordering was necessary
    else:
        return movie_title


def extract_release_year_from_title(movie_title: str):
    """
    Extracts the release year of a movie from its title.

    :param movie_title: title from which the release year should be extracted from
    :return: year - the release year
    """

    # find the indices of the brackets by searching the reversed title (to be sure to get the correct sets of
    # brackets if there is a release year)
    opening_parenthesis_index = movie_title[::-1].find("(")
    closing_parenthesis_index = movie_title[::-1].find(")")
    # check if there is a bracket and the first char in the bracket is a number
    if closing_parenthesis_index != -1 and re.search(movie_title[::-1][opening_parenthesis_index - 1],
                                                     "0123456789") is not None:
        year = movie_title[::-1][closing_parenthesis_index + 1:opening_parenthesis_index][::-1]
        # if the year is a range (e.g. "(2006-2007)"), use the first year for the database
        if len(year) > 4:
            year = movie_title[::-1][opening_parenthesis_index - 4:opening_parenthesis_index][::-1]
    else:
        # if there is no bracket or the first char is not a number, set the year to NaN
        year = math.nan

    return year


def check_and_read_data(db: sqlalchemy, testing: bool = False):
    """
    Checks the data of the MovieLens dataset for duplicates and reads it into the database.

    :param db: database to be populated
    :param testing: if set to True, only a subset of the data is checked and read in to reduce computing time for
    testing
    """

    # check if we have movies in the database
    # read data if database is empty
    if Movie.query.count() == 0:
        # read movies from csv
        # region movies
        with open('data/movies.csv', newline='', encoding='utf8') as csvfile:
            reader = csv.reader(csvfile, delimiter=',')
            count = 0
            for row in reader:
                if count > 0:
                    try:
                        movie_id = row[0]
                        title = get_clean_movie_title(row[1])
                        # extract the release year
                        year = extract_release_year_from_title(title)
                        movie = Movie(id=movie_id, title=title, release_year=year, amount_of_ratings=math.nan,
                                      average_rating=math.nan)
                        db.session.add(movie)
                        genres = row[2].split('|')
                        for genre in genres:
                            if "(no genres listed)" in genre:
                                genre = math.nan
                            movie_genre = MovieGenre(movie_id=movie_id, genre=genre)
                            db.session.add(movie_genre)
                        db.session.commit()
                    except IntegrityError:
                        print("Ignoring duplicate movie: " + title)
                        db.session.rollback()
                        pass
                count += 1
                if count % 100 == 0:
                    print(count, " movies read")
        # endregion
        # region ratings
        with (open('data/ratings.csv', newline='', encoding='utf8') as csvfile):
            if testing:
                num_of_rows = sum(1 for _ in csvfile)
                skip_rows = random.sample(range(1, num_of_rows + 1), num_of_rows-7500)
                reader = pd.read_csv('data/ratings.csv', skiprows=skip_rows, delimiter=",")
                count = 0
                for row in reader.iterrows():
                    if count > 0:
                        movie_rating = MovieRating(movie_id=int(row[1].iloc[1]), user_id=int(row[1].iloc[0]),
                                                   rating=row[1].iloc[2], time_rated=row[1].iloc[2], ignored=False,
                                                   time_ignored=math.nan)
                        db.session.add(movie_rating)
                        db.session.commit()
                        try:
                            user = User(id=int(row[1].iloc[0]), active=False, username="User" + str(int(row[1].iloc[0])),
                                        initialized_scores=False)
                            db.session.add(user)
                            db.session.commit()
                        except IntegrityError:
                            db.session.rollback()
                            pass
                    count += 1
                    if count % 100 == 0:
                        print(count, " ratings read")
            else:
                reader = csv.reader(csvfile, delimiter=',')
                count = 0
                for row in reader:
                    if count > 0:
                        movie_rating = MovieRating(movie_id=row[1], user_id=row[0], rating=row[2], time_rated=row[3],
                                                   ignored=False, time_ignored=math.nan)
                        db.session.add(movie_rating)
                        db.session.commit()
                        try:
                            user = User(id=row[0], active=False, username="User"+str(row[0]), initialized_scores=False)
                            db.session.add(user)
                            db.session.commit()
                        except IntegrityError:
                            db.session.rollback()
                            pass
                    count += 1
                    if count % 100 == 0:
                        print(count, " ratings read")
        # endregion
        # region links
        with open('data/links.csv', newline='', encoding='utf8') as csvfile:
            reader = csv.reader(csvfile, delimiter=',')
            count = 0
            for row in reader:
                if count > 0:
                    links = Links(movie_id=row[0], imdb_id=row[1], tmdb_id=row[2])
                    db.session.add(links)
                    db.session.commit()
                count += 1
                if count % 100 == 0:
                    print(count, " links read")
        # endregion
        # region tags
        with open('data/tags.csv', newline='', encoding='utf8') as csvfile:
            reader = csv.reader(csvfile, delimiter=',')
            count = 0
            for row in reader:
                if count > 0:
                    try:
                        tag = row[2].upper()
                        tags = Tags(user_id=row[0], movie_id=row[1], tag=tag, timestamp=row[3])
                        db.session.add(tags)
                        db.session.commit()
                    except IntegrityError:
                        print("Ignoring duplicate tag: " + tag)
                        db.session.rollback()
                        pass
                count += 1
                if count % 100 == 0:
                    print(count, " tags read")
        # endregion
