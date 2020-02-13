import datetime
import math
import random
from datetime import timedelta

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


class BaseSurvey():
    def __init__(self, db, batch_size, lang, intervention_name, intervention_type, config):
        """
        :param db:  connection to make use of
        :param batch_size:
        :param lang:
        :param intervention_name:
        :param intervention_type:
        :return: new_actions a list of orm objects of added users, continuation information
        """
        self.db = db
        self.batch_size = batch_size
        self.lang = lang
        self.intervention_name = intervention_name
        self.intervention_type = intervention_type
        self.config = config
        self.experiment_name = self.config['name']
        self.experiment_id = _get_experiment_id(self.db, self.experiment_name, return_id=True)
        self.now = datetime.datetime.utcnow()
        self.survey_after_days = self.config['survey_settings']['survey_after_days']
        self.action_latest_date = self.now - datetime.timedelta(days=self.survey_after_days)
        self.new_actions = []

    def run(self):
        logging.info(f'Starting to run the survey creator at {self.now}')

        ## check if we are done:
        if self._check_survey_sending_already_done():
            return self.new_actions

        users_needing_survey = self._get_unsent_survey_recipients()

        # batch and deduplication
        users_needing_survey = self._dedupe_users_needing_survey(users_needing_survey)
        users_needing_survey = self._batch_trim_users_needing_survey(users_needing_survey)

        # create EAS and store them in self.new_actions
        survey_experiment_actions = self._create_survey_experiment_actions(users_needing_survey,
                                                                           self.extra_metadata_fields)
        self.new_actions.extend(survey_experiment_actions)

        return self.new_actions

    def _check_survey_sending_already_done(self):
        if 'max_surveys' in self.config['survey_settings'].keys():
            num_experiment_actions = _get_num_experiment_actions(self.db, action=self.intervention_name)
            if num_experiment_actions >= self.config['survey_settings']['max_surveys']:
                logging.info('Already sent maximum surveys, nothing to do')
                return True
        else:
            return False

    def _get_sent_survey_recipient(self):
        q = self.db.query(ExperimentAction) \
            .filter(ExperimentAction.experiment_id == self.experiment_id) \
            .filter(ExperimentAction.action_subject_type == self.intervention_type) \
            .filter(ExperimentAction.action_subject_id == self.intervention_name)
        return q.all()

    def _get_unsent_survey_recipients(self):
        raise NotImplementedError

    def _get_item_or_attr(self, obj, item_or_attr):
        if hasattr(obj, 'metadata_json'):
            return obj.metadata_json[item_or_attr]
        elif hasattr(obj, '__getitem__'):
            return obj[item_or_attr]
        elif hasattr(obj, item_or_attr):
            return obj.item_or_attr

    def _create_survey_experiment_actions(self, users_needing_survey, extra_metadata_fields):
        experiment_actions = []
        for user in users_needing_survey:

            user_name = self._get_item_or_attr(user, 'user_name')

            metadata_json = {"lang": self.lang,
                             "user_name": user_name}
            for extra_metadata_field in extra_metadata_fields:
                metadata_json[extra_metadata_field] = self._get_item_or_attr(user, extra_metadata_field)

            experiment_action = ExperimentAction(experiment_id=self.experiment_id,
                                                 action_object_id=user_name,
                                                 action_object_type=ThingType.WIKIPEDIA_USER,
                                                 action_subject_id=self.intervention_name,
                                                 action_subject_type=self.intervention_type,
                                                 action_platform=PlatformType.WIKIPEDIA,
                                                 # action_key_id=randomization_arm,
                                                 action=self.intervention_type,
                                                 metadata_json=metadata_json)
            experiment_actions.append(experiment_action)
        self.db.add_all(experiment_actions)
        self.db.commit()
        logging.info(f'Commited {len(experiment_actions)} experiment experiment_actions')
        return experiment_actions

    def _dedupe_users_needing_survey(self, users_needing_survey):
        # raise NotImplementedError
        return users_needing_survey

    def _batch_trim_users_needing_survey(self, users_needing_survey):
        # raise NotImplementedError
        return users_needing_survey
