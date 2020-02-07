import datetime
from uuid import uuid4

from civilservant.wikipedia.connections.api import get_mwapi_session, get_auth
from civilservant.wikipedia.queries.sites import get_new_users
import civilservant.logs

civilservant.logs.initialize()
import logging

from thanks.creators import BaseSurvey


class FrenchWelcomePilotSurvey(BaseSurvey):
    """
    this survey assumes to be run once per day.
    """

    def __init__(self, db, batch_size, lang, intervention_name, intervention_type, config):
        super().__init__(db, batch_size, lang, intervention_name, intervention_type, config)
        self.mwapi_session = get_mwapi_session(lang=lang)
        self.auth = get_auth()
        self.assumed_cron_interval_days = 1
        self.extra_metadata_fields = []

    def _get_unsent_survey_recipients(self):
        # we want to get from the API users who registered between
        # self.action_latest_date and self.action_latest_date - days(1)

        start_time = self.action_latest_date
        end_time = self.action_latest_date - datetime.timedelta(days=self.assumed_cron_interval_days)
        historic_new_users = get_new_users(self.mwapi_session, end_time=end_time, start_time=start_time)
        historic_create_users = [hnu for hnu in historic_new_users if hnu['action'] == 'create']
        logging.info(f'Found {len(historic_create_users)} historic create users who were created between'
                     f'{end_time} and {start_time}')

        self.extra_metadata_fields.append('public_anonymous_id')

        for hcu in historic_create_users:
            hcu['public_anonymous_id'] = str(uuid4())
        return historic_create_users


def fr_wiki_welcome_pilot_survey(db, batch_size, lang, intervention_name, intervention_type, config):
    fwps = FrenchWelcomePilotSurvey(db, batch_size, lang, intervention_name, intervention_type, config)
    return fwps.run()
