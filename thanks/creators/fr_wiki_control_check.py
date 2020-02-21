import datetime
from uuid import uuid4

from civilservant.models.core import ExperimentAction
from civilservant.wikipedia.connections.api import get_mwapi_session, get_auth
from civilservant.wikipedia.queries.sites import get_new_users
import civilservant.logs
from sqlalchemy import and_

civilservant.logs.initialize()
import logging

from thanks.creators import BaseSurvey


class FrenchControlCheck(BaseSurvey):
    """
    this survey assumes to be run once per day.
    """

    def __init__(self, db, batch_size, lang, intervention_name, intervention_type, config):
        super().__init__(db, batch_size, lang, intervention_name, intervention_type, config)

    def _get_unsent_survey_recipients(self):
        # we want to get from the API users who registered between
        # self.action_latest_date and self.action_latest_date - days(1)

        start_time = self.action_latest_date
        logging.info(f'Looking for control users before {start_time}, with expid {self.experiment_id}, action key id {0} actin')

        control_criteria = and_(ExperimentAction.experiment_id == self.experiment_id,
                                ExperimentAction.action_key_id == 0, # control contiditon
                                ExperimentAction.action_subject_type == 'talk_page_message',
                                ExperimentAction.created_dt <= start_time)
        checked_criteria = and_(ExperimentAction.experiment_id == self.experiment_id,
                                ExperimentAction.action_subject_id == self.intervention_name,
                                ExperimentAction.action_subject_type == self.intervention_type)

        control_users = self.db.query(ExperimentAction).filter(control_criteria).all()
        checked_users = self.db.query(ExperimentAction).filter(checked_criteria).all()

        checked_user_names = [checked.metadata_json['user_name'] for checked in checked_users]
        unchecked_control_users = [cu for cu in control_users if not cu.metadata_json['user_name'] in checked_user_names]

        return unchecked_control_users


def fr_wiki_control_check(db, batch_size, lang, intervention_name, intervention_type, config):
    fcc = FrenchControlCheck(db, batch_size, lang, intervention_name, intervention_type, config)
    return fcc.run()
