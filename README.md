# AIWeb Project 2 - Movie Recommender

# _MovieRex_ - a movie recommender
The second project by Cosima Oprotkowitz and Isabel Grauwelman (Group 34) for the seminar "AI and the Web" taught by Dr. Tobias Thelen in WS2023/24 at the University of Osnabrück.


## Link
_MovieRex_ is accessible via a Osnabrück University server connection at http://vm146.rz.uni-osnabrueck.de/user056/recommender.wsgi


## Description
_MovieRex_ is a movie recommender that (obviously) recommends movies for a user, incorporating survey-given preferences, similarities between movies, similarity to other users and further exploration of the movies in the database. The movies are displayed with information on their title, release year, genres and tags and their average ratings in the database. For this, the [MovieLens dataset](https://grouplens.org/datasets/movielens/latest/) was used.

The user can rate movies with 1.0 to 5.0 stars (in 0.5 steps). They can also ignore movies, which means that the movie will not be taken into account for future recommendations (If it has already been rated, the movie will be 'deleted' from the user's preferences and the average movie rating will be recalculated as a means to also ignore the rating. If it has no rating, it will not be recommended to the user anymore). For additional options to find new movies, the user can search via a search bar or filter through all movies in the database for a specific genre and/or decade. For a better overview, the user can access lists of all their rated and ignored movies as well as putting movies on a watchlist. The user also gets an overview of their preferences, both from their ratings and their survey, with the option to edit the latter.


_MovieRex_ was built as a flask application and deployed via a WSGI server.

## Files
**`data`** folder:
- `links.csv`, `movies.csv`, `rating.csv`, `tags.csv` - MovieLens data files
- `README.txt` - MovieLens README file

**`static`** folder:
- `img/rex.png` - the logo
- `style01.css` - style sheet for all templates


**`templates`** folder:
- `flask_user_layout.html` - general template from which most of the other templates extend (was edited, but already part of the recommender base that was provided as a starting point)
- `home01.html` - home page when the user is not logged in (anymore) with options to register and sign in
- `home.html` - home page when the user is logged in, showing their recommendations, a user dropdown, and search and filter options
- `loading.html` - loading screen after the home page has been reloaded/loaded from another page
- `survey.html` - a survey about the user's (dis-)liked genres that appears as the first page after registering and that is linked on the preference page, to allow the user to edit it
- `survey_submit.html` - loading screen after the survey has been submitted
- `watchlist.html` - template with all movies that the user added to the watchlist
- `rated_movies.html` - template with all movies the user has rated
- `ignored_movies.html` - template with all movies the user has chosen to ignore for the recommendations
- `preferences.html` - template with the user's preferences from their rating and their survey, including the link to edit the survey
- `filter.html` - template that shows results from the filter option on the home and filter page which can be used to filter through all movies by decade and/or genre
- `search_results.html` - displays the results if the user searched via the search bar
- `added.html`, `removed.html`, `rated.html` - templates that are used for the dynamic display of content, i.e. the adding and removing from the database and the rating, respectively

**`get_data.py`**: contains helper functions that read out data from the database

**`models.py`**: contains classes that define the database tables

**`preparation`**: contains functions that are called after the database is read in for preprocessing and the function for initializing the UserMovieRecommendationScores entries for a new user

**`read_data.py`**: contains functions that read the MovieLens data into the database while checking for duplicates and extracting the correct information

**`recommendation.py`**: contains the functions for the recommendation algorithm which is explained in the section "How does it work?" below

**`recommender.py`**: contains all views/routes for the application connecting backend and frontend

**`recommender.wsgi`**: WSGI file of the app for the server application

**`requirements.txt`**: lists the required packages that need to be installed beforehand to make the application work

**`searcher.py`**: contains the functions for the search function

**`utils.py`**: contains all helper functions


## Installation
Do not forget to install the requirements beforehand via 'pip install -r requirements.txt'.

In case the html templates are given out with the wrong styles, hold down 'Strg/Ctrl'+'Shift'+'R' or 'Strg/Ctrl'+'F5' (in Windows/Linux) or 'Command'+'Alt'+'R' (in Apple) for a hard refresh of the page (and the cached files).


## How does it work?
The recommendation algorithm used for _MovieRex_ is a Collaborative Filtering algorithm that combines Memory-Based User-User
and Item-Item methods with results from user-selected preferences and explorative recommendations. For each movie in the database,
a score is calculated for each of the methods individually, which are combined in the form of a weighted sum for the hybrid
recommendations that are displayed to the user on their home page in case they rated a minimum amount of movies that the recommendations
can be based on. All scores of the movies that the user liked or ignored are set to 0.  
Based on the user's actions, the individual scores or only some of them are recalculated. The following overview shows the different actions
available for the user that influences at least one of the sub-scores or the total recommendation score and which of the scores need to be recalculated as a result:

| Action                                  | Survey-based score                                      | Exploration-based score                                 | User-based score                                        | Item-based score                                        | Total recommendation score                              |
|-----------------------------------------|---------------------------------------------------------|---------------------------------------------------------|---------------------------------------------------------|---------------------------------------------------------|---------------------------------------------------------|
| submitted preference survey (not empty) | <center>yes</center>                                    | <center>no</center>                                     | <center>no</center>                                     | <center>no</center>                                     | <center>yes</center>                                    |
| emptied the preference survey           | <center>(yes)<br/>_reset scores_</center>               | <center>no</center>                                     | <center>no</center>                                     | <center>no</center>                                     | <center>yes</center>                                    |
| rated a movie                           | <center>(no)<br/>_set score of the movie to 0_</center> | <center>yes</center>                                    | <center>yes</center>                                    | <center>yes</center>                                    | <center>yes</center>                                    |
| ignored a rated movie                   | <center>no</center>                                     | <center>yes<sup>1</sup></center>                        | <center>yes</center>                                    | <center>yes</center>                                    | <center>yes</center>                                    |
| ignored an unrated movie                | <center>(no)<br/>_set score of the movie to 0_</center> | <center>(no)<br/>_set score of the movie to 0_</center> | <center>(no)<br/>_set score of the movie to 0_</center> | <center>(no)<br/>_set score of the movie to 0_</center> | <center>(no)<br/>_set score of the movie to 0_</center> |
| "un"-ignored a movie (rated or unrated) | <center>no</center>                                     | <center>yes<sup>1</sup></center>                        | <center>yes<sup>2</sup></center>                        | <center>yes<sup>2</sup></center>                        | <center>yes</center>                                    |

<sup>1</sup> If a rated movie is ("un"-)ignored, the average rating of it needs to be recalculated 
(excluding/including the rating of the user). If the method concerns the underexplored genres, 
the score needs to be recalculated as the removal/adding of the ignored movie's genres might have 
changed the numbers significantly.  
<sup>2</sup> If a rated movie is "un"-ignored, the movie's features (genres and decades) and the user's 
rating need to be re-added to the database. This can result in significant changes of the score.
If an unrated movie is "un"-ignored, the score needs to be recalculated to include the movie in the
recommendations again.

<br>

#### Survey-based: Preference survey
As a solution to the cold start problem, the user is prompted to fill out a survey after registering in which they should
select genres they usually enjoy and usually do not enjoy watching. However, it is also possible to skip the survey, in which 
case only explorative recommendations are given.  
The survey-based score is an equally weighted sum of two parts:  

(1) _ratio of liked genres (as selected in the survey)_ - how many of a movie's genres are part of the liked genres?  
(2) _amount of ratings_ - amount of ratings for a movie, cast dynamically to the score with values between 0.0 and 1.0 

The second part was added to make the score more diverse as a way to sort the movies more meaningfully for the user.
If a movie's genre includes at least one of the genres the user selected as disliked in the survey, the survey-based score is set to 0 as
the disliked genres are phrased as genres that should be excluded and thus it should not matter if a movie's genres also include genres 
they selected as liked.  
Casting a value that is bound to a specific range to another range is generally done via the following formula:  
```
((value to be cast - min. value original range) / (max. value original range - min. original range)) + (max. value new range - min. value new range) + min. value new range
``` 
With the range of the amount of ratings being (0, max. amount of ratings) and the range of the score being (0.0, 1.0),
the simplified calculation for the second part is thus:
```
amount of ratings to be cast / max. amount of ratings
```

<br>

__Example:__ The maximum amount of ratings in the database are 20, and the user selected the following genres in the survey:

| Liked genres | Disliked genres |
|--------------|-----------------|
| Comedy       | Horror          |
| Children's   | Animation       |
| Fantasy      | Documentary     |   

For movies A, B and C the survey-based score would be:

| Movie              | Genres                              | Amount<br/>of ratings | Survey-based<br/>score                             |
|--------------------|-------------------------------------|-----------------------|----------------------------------------------------|
| <center>A</center> | Comedy<br/>Children's<br/>Animation | <center>5</center>    | <center>0<center>                                  |
| <center>B</center> | Comedy<br/>Romance<br/>Action       | <center>12</center>   | <center>0.5 * (1/3) + 0.5 * (12/20) = 0.47<center> |
| <center>C</center> | Children's<br/>Fantasy<br/>Action   | <center>10</center>   | <center>0.5 * (2/3) + 0.5 * (10/20) = 0.58<center> |


<br>

#### Exploration-based: Popular movies / Underexplored genres
As another solution to the cold start problem, the recommendations that are shown to the user will consist of the most popular
movies in the database in case the user did not fill out the preference survey. For the popularity, the amount of ratings and the
average rating are considered. The latter needs to be at least 4.0 for a movie to be deemed popular in this context.
The exploration-based score is also an equally weighted sum of two parts:  

(1) _average rating_ - average rating of a movie, cast dynamically to the score with values between 0.0 and 1.0  
(2) _amount of ratings_ - amount of ratings for a movie, cast dynamically to the score with values between 0.0 and 1.0    

The second part was added again for the sake of ordering the recommendations more meaningfully for the user. It is calculated via the simplified
formula shown in the previous paragraph.
Using the casting for the first part as well, for which we have the original average rating range of (4.0, 5.0), 
as the minimum average rating for a popular movie is 4.0, and the new score range (0.0, 1.0), the simplified calculation is:
```
average rating to be cast - 4.0
```
<br>

__Example:__ The maximum amount of ratings in the database are 20. For movies A, B and C the exploration-based score for the
popular movies would be: 

| Movie              | Average rating        | Amount<br/>of ratings | Exploration-based<br/>score                             |
|--------------------|-----------------------|-----------------------|---------------------------------------------------------|
| <center>A</center> | <center>4.5</center>  | <center>5</center>    | <center>0.5 * (4.5 - 4.0) + 0.5 * (5/20) = 0.38<center> |
| <center>B</center> | <center>5.0</center>  | <center>12</center>   | <center>0.5 * (5.0 - 4.0) + 0.5 * (12/20) = 0.8<center> |
| <center>C</center> | <center>4.35</center> | <center>10</center>   | <center>0.5 * (4.35-4.0) + 0.5 * (10/20) = 0.43<center> |


If the user rated at least 50 movies, the exploration-based score will be related to the user's underexplored genres instead. Given their 
ratings, genres that they did not rate any movies of or genres of which the user's ratings maximally make up 10% of all their ratings will be
identified and used as a baseline. The exploration-based score is then calculated as a ratio of underexplored genres. If none of a movies
genres are part of the underexplored genres of the user, the score is set to 0.0.

<br> 

__Example:__ The following genres are identified as underexplored of the user:

| Underexplored genres |
|----------------------|
| Drama                |
| IMAX                 |
| Thriller             |   

For movies A, B and C the exploration-based score for the underexplored genres would be:

| Movie              | Genres                           | Exploration-based<br/>score |
|--------------------|----------------------------------|-----------------------------|
| <center>A</center> | Drama<br/>Romance<br/>Animation  | <center>1/3 = 0.33<center>  |
| <center>B</center> | Children's<br/>IMAX<br/>Drama    | <center>2/3 = 0.67<center>  |
| <center>C</center> | Adventure<br/>Fantasy<br/>Action | <center>0<center>           |


<br>

#### User-based: Movies similar users liked
One of the Collaborative Filtering methods used for _MovieRex_ is the User-User method. With it, similar users
to the target user are identified to be able to identify movies those users liked as it is likely that the
target user will like these movies as well. A movie is considered to be liked if it got a rating of at least 4.0.  
The user-based score is not a range of scores as the other scores; instead, movies that exact matches liked will
get a score of 1.0, movies that similar users liked will get a score of 0.75 and all other movies will get a score of
0.0.
The similarity between users is calculated by creating a user-movie matrix with the rows being sparse
rating vectors of all users and then getting the Euclidean Distance (ignoring NaN values) between the user's vectors.
If this distance is 0, the corresponding user is an exact match, and if the distance is greater than zero but maximally 30,
the corresponding user is a similar user to the target user.

<br>

#### Item-based: Movies similar to liked movies
The other Collaborative Filtering method used is the Item-Item method. With this method, similar movies to the
ones the user rated with at least 4.0 are identified as recommendations. For this, the amount of ratings, likes and dislikes are
saved in the database tables UserGenrePreferences and UserDecadePreferences, respectively, i.e. for both each genre in the database
and for each decade from 1900 to 2020. From the entries, liked ratios and disliked ratios are calculated, i.e. which proportion of the
rated movies with a specific genre the user liked (i.e. rating of at least 4.0), and which proportion of them they disliked (i.e. 
rating of at most 2.0); same for the decade the movie's release year belongs to. The item-based score is the sum of the genre-based score 
and the decade-based score, clamped between 0.0 and 1.0.  
The genre-based score is calculated as the equally weighted sum of the following formula for each genre:  
```
1 * liked ratio of the genre + (-1) * disliked ratio of the genre
```
The decade-based score is calculated by the same formula:
```
1 * liked ratio of the decade + (-1) * disliked ratio of the decade
```
Both sub-scores may be negative so that the total item-based score is also influenced by the user's dislikes.

<br>

__Example:__ The following data is recorded for the user (all other genres and decades were not rated yet):

| Genre      | Amount<br/>of ratings | Amount<br/>of likes | Amount<br/>of dislikes |    | Decade  | Amount<br/>of ratings | Amount<br/>of likes | Amount<br/>of dislikes |
|------------|-----------------------|---------------------|------------------------|----|---------|-----------------------|---------------------|------------------------|  
| Comedy     | <center>10<center>    | <center>8<center>   | <center>1<center>      |    | 1990    | <center>3<center>     | <center>3<center>   | <center>0<center>      |
| Children's | <center>7<center>     | <center>7<center>   | <center>0<center>      |    | 2000    | <center>13<center>    | <center>9<center>   | <center>1<center>      |
| Thriller   | <center>5<center>     | <center>0<center>   | <center>4<center>      |    | 2010    | <center>6<center>     | <center>3<center>   | <center>3<center>      |

This results in the following ratings:

| Genre      | Liked ratio                | Disliked ratio             |   | Decade | Liked ratio                 | Disliked ratio              |
|------------|----------------------------|----------------------------|---|--------|-----------------------------|-----------------------------|
| Comedy     | <center>8/10 = 0.8<center> | <center>1/10 = 0.1<center> |   | 1990   | <center>3/3 = 1.0<center>   | <center>0/3 = 0.0<center>   |
| Children's | <center>7/7 = 1.0<center>  | <center>0/7 = 0.0<center>  |   | 2000   | <center>9/13 = 0.69<center> | <center>1/13 = 0.08<center> |
| Thriller   | <center>0/5 = 0.0<center>  | <center>4/5 = 0.8<center>  |   | 2010   | <center>3/6 = 0.5<center>   | <center>3/6 = 0.5<center>   |

For movies A, B and C the item-based score would then be:

| Movie              | Decade | Genres                                      | Genre-based<br/>score                                                                                                                                                                                                                | Decade-based<br/>score                             | Item-based<br/>score                                               |
|--------------------|--------|---------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------|--------------------------------------------------------------------|
| <center>A</center> | 2010   | Children's<br/>Romance<br/>Animation        | <center>(1/3) * (1 * 1.0 + (-1) * 0.0)<br/>+ (1/3) * (1 * 0.0 + (-1) * 0.0)<br/>+ (1/3) * (1 * 0.0 + (-1) * 0.0)<br/>= (1/3) * 1.0 + (1/3) * 0.0 + (1/3) * 0.0<br/>= 0.33<center>                                                    | <center>1 * 0.5 + (-1) * 0.5<br/>= 0</center>      | <center>0.33 + 0 = 0.33</center>                                   |
| <center>B</center> | 1990   | Children's<br/>Comedy<br/>Drama<br/>Fantasy | <center>(1/4) * (1 * 1.0 + (-1) * 0.0)<br/>+ (1/4) * (1 * 0.8 + (-1) * 0.1)<br/>+ (1/4) * (1 * 0.0 + (-1) * 0.0)<br/>+ (1/4) * (1 * 0.0 + (-1) * 0.0)<br/>= (1/4) * 1.0 + (1/4) * 0.7 + (1/4) * 0.0 + (1/4) * 0.0<br/>= 0.43<center> | <center>1 * 1.0 + (-1) * 0.0<br/>= 1.0</center>    | <center>0.43 + 1.0<br/>= 1.43<br/>_1.43 > 1.0_<br/>=> 1.0</center> |
| <center>C</center> | 2000   | Thriller<br/>Action                         | <center>(1/2) * (1 * 0.0 + (-1) * 0.8)<br/>+ (1/2) * (1 * 0.0 + (-1) * 0.0)<br/>= (1/2) * (-0.8) + (1/2) * 0.0<br/>= -0.4<center>                                                                                                    | <center>1 * 0.69 + (-1) * 0.08<br/>= 0.61</center> | <center>(-0.4) + 0.61<br/>= 0.21</center>                          |

<br>

#### Hybrid: Weighted sum of the sub-scores
The recommendations that are displayed on the user's home page are the results of the hybrid recommendation score calculation.
For this, All previous sub-scores (survey-based, exploration-based, user-based and item-based) are combined via a weighted
sum to get the total recommendation score for a movie. If the user filled out the preference survey, the weights are **0.25 for the survey-based
score**, **0.15 for the exploration-based score**, and **0.3 for the user-based and the item-based score**, respectively. If the user did
not fill out (or emptied) the preference survey, the weights are **0.2 for the exploration-based score** and **0.4 for the user-based score and the
item-based score**, respectively, instead. The weights were chosen so that the explorative recommendations do not make up a lot of the
results while still being present for the user, and so that the survey has less weight than the user-based and the item-based
recommendations in case the user's preferences evolve over time and they forget to update their responses. For optimal results, the
weighting should be tested and optimized based on user feedback.  

<br>

__Example:__ The total recommendation score for movies A, B and C would be:

| Movie              | Survey-based<br/>score                                            | Exploration-based<br/>score | User-based<br/>score | Item-based<br/>score  | Total<br/>score                                                                                                                                                                              |
|--------------------|-------------------------------------------------------------------|-----------------------------|----------------------|-----------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| <center>A</center> | <center>0.42 (filled out)<br/>_____________<br/>0 (else)</center> | <center>0.3</center>        | <center>0.75<center> | <center>0.63</center> | <center>0.25 * 0.42<br/>+ 0.15 * 0.3<br/>+ 0.3 * 0.75<br/>+ 0.3 * 0.63<br/>= 0.56 (with survey)<br/>_____________<br/>0.2 * 0.3<br/>+ 0.4 * 0.75<br/>+ 0.4 * 0.63<br/>= 0.61 (else)</center> |
| <center>B</center> | <center>0.2 (filled out)<br/>_____________<br/>0 (else)</center>  | <center>0.93</center>       | <center>0.0<center>  | <center>0.19</center> | <center>0.25 * 0.2<br/>+ 0.15 * 0.93<br/>+ 0.3 * 0.0<br/>+ 0.3 * 0.19<br/>= 0.25 (with survey)<br/>_____________<br/>0.2 * 0.93<br/>+ 0.4 * 0.0<br/>+ 0.4 * 0.19<br/>= 0.26 (else)</center>  |
| <center>C</center> | <center>0.78 (filled out)<br/>_____________<br/>0 (else)</center> | <center>0.46</center>       | <center>1.0<center>  | <center>0.87</center> | <center>0.25 * 0.78<br/>+ 0.15 * 0.46<br/>+ 0.3 * 1.0<br/>+ 0.3 * 0.87<br/>= 0.83 (with survey)<br/>_____________<br/>0.2 * 0.46<br/>+ 0.4 * 1.0<br/>+ 0.4 * 0.87<br/>= 0.84 (else)</center> |

<br>

## Suggestions for improvements
### content-wise ideas
- the tags could be included in the recommendations and/or be filtered by the user
- age restrictions/ratings could be displayed with the movies (R-rated, etc.)
- more information on the film could be displayed, e.g. through a pop up
- a "find similar movies" function that works on specific/individual movies could be included
- the application could get more of a journal function, where users could also log the data of when they have watched a movie and add reviews in addition to the ratings - if this was the case, the users could get more statistics about their behavior/logged data

### technical-wise ideas
- for explorative recommendations: get recommendations with movies that have very few ratings overall instead if a user does not have underexplored genres
- the application could load faster (somehow)
- recently rated movies could be weighted more for new recommendations and similarly the survey could lose weight with more time passing, as preferences might change with time
- the application could be optimized for different devices and screens
- allow users to delete their profile and the database entries related to it

