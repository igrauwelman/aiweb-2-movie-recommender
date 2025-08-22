from flask_login import current_user

from models import UserGenrePreferences


def check_whether_there_are_survey_entries():
	"""
	Checks whether there are survey responses saved in the database by the current user.

	:return: True if there are entries, False if there are none
	"""

	# get the rows in UserGenrePreferences corresponding to the current user
	preference_rows = UserGenrePreferences.query.filter(UserGenrePreferences.user_id == current_user.id).all()
	# go through each row and check the survey_response attribute
	for row in preference_rows:
		# if there is a row for which the attribute is not None, return True as there is at least one entry
		if row.survey_response is not None:
			return True
	# return False as the attribute is None for each row, i.e. there are no survey responses
	return False
