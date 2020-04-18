import datetime
import math
import random
from datetime import timedelta
from uuid import uuid4

from civilservant.wikipedia.connections.api import get_mwapi_session, get_auth
from civilservant.wikipedia.queries.sites import get_new_users, get_volunteer_signing_users
from civilservant.models.core import Experiment, ExperimentThing, ExperimentAction
from civilservant.models.wikipedia import WikipediaUser
from civilservant.util import ThingType, PlatformType
from sqlalchemy.orm import aliased

from thanks.utils import _get_experiment_id, _get_num_experiment_actions

import civilservant.logs
from sqlalchemy import func, desc, and_

civilservant.logs.initialize()
import logging

from thanks.creators import BaseSurvey


class ActionFollowUpSurvey(BaseSurvey):
    def __init__(self, db, batch_size, lang, intervention_name, intervention_type, config):
        super().__init__(db, batch_size, lang, intervention_name, intervention_type, config)
        self.extra_metadata_fields = ['public_anonymous_id']

    def _get_completed_interventions(self):
        # join on what should be be the wikipedia user id en EA and ETs
        intervention_on_clause = and_(ExperimentAction.action_object_id == ExperimentThing.thing_id,
                                      ExperimentAction.metadata_json['lang'] ==
                                      ExperimentThing.metadata_json['sync_object']['lang'])

        intervention_completed_qualify = and_(ExperimentAction.experiment_id == self.experiment_id,
                                              ExperimentAction.action_subject_id == self.survey_after_intervention,
                                              ExperimentAction.action_subject_type == self.survey_after_intervention_type,
                                              ExperimentAction.created_dt < self.action_latest_date,
                                              ExperimentAction.metadata_json['action_complete'] == True)

        completed_intervention_users_res = self.db.query(ExperimentAction, ExperimentThing) \
            .join(ExperimentThing, intervention_on_clause) \
            .filter(intervention_completed_qualify).all()

        completed_intervention_users = self._dictify_completed_intervention_users(completed_intervention_users_res)

        return completed_intervention_users

    def _dictify_completed_intervention_users(self, completed_intervention_users_res):
        completed_intervention_users = []
        for ea, et in completed_intervention_users_res:
            ciu = {'user_name':
                       ea.metadata_json['user_name'], }
            completed_intervention_users.append(ciu)
        return completed_intervention_users

    def _get_unsent_survey_recipients(self):
        """
        find which users need need to receive surveys that haven't already
        :rtype dict to map to ExperimentActions
        """
        logging.info(f'Seeking welcomed users that havent been surveyed before {self.action_latest_date}')

        # welcome
        completed_intervention_users = self._get_completed_interventions()

        sent_survey_recipients = super()._get_sent_survey_recipient()

        sent_survey_user_names = [ea.metadata_json['user_name'] for ea in sent_survey_recipients]

        unsent_survey_recipients = [ciu for ciu in completed_intervention_users if
                                    ciu['user_name'] not in sent_survey_user_names]

        for usr in unsent_survey_recipients:
            usr['public_anonymous_id'] = str(uuid4())
        return unsent_survey_recipients


def fr_wiki_welcome_survey(db, batch_size, lang, intervention_name, intervention_type, config):
    afus = ActionFollowUpSurvey(db, batch_size, lang, intervention_name, intervention_type, config)
    return afus.run()
