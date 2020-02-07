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

from thanks.creators import BaseSurvey

class ActionFollowUpSurvey(BaseSurvey):

    def _get_unsent_survey_recipients(self):
        """
        find which users need need to receive

        ExperimentThing | ExpeimentAction | ExperimentActionSurvey
             thing_id <--> action_obj_id
                      metadata$user_name <--> action_object_id

        """
        logging.info(f'Seeking thankees who received thanks before {self.action_latest_date}')

        ExperimentActionSurvey = aliased(ExperimentAction)

        # welcome
        action_complete_onclause = and_(ExperimentAction.action_object_id == ExperimentThing.thing_id,
                                        ExperimentAction.metadata_json['lang'] ==
                                        ExperimentThing.metadata_json['sync_object']['lang'])

        # the we make sure the action_object_id is in the survey
        survey_sent_onclause = and_(ExperimentActionSurvey.action_object_id == \
                                    ExperimentAction.metadata_json['user_name'],
                                    ExperimentActionSurvey.metadata_json['lang'] ==
                                    ExperimentAction.metadata_json['lang'])

        action_complete_qualify = and_(ExperimentAction.experiment_id == -15,
                                       ExperimentAction.action == 'talk_page_message',
                                       ExperimentAction.created_dt < self.action_latest_date,
                                       ExperimentAction.metadata_json['action_complete'] == True)

        relevant_surveys = and_(ExperimentActionSurvey.action_subject_id == self.intervention_name,
                                ExperimentActionSurvey.action == self.intervention_type)

        # the first join is to get users with their action complte
        action_completed_p = self.db.query(ExperimentAction, ExperimentThing, ExperimentActionSurvey) \
            .join(ExperimentThing, action_complete_onclause) \
            .filter(action_complete_qualify)

        # the second join is to get users who have been sent surveys
        action_completed_q = action_completed_p \
            .outerjoin(ExperimentActionSurvey, survey_sent_onclause) \
            .filter(relevant_surveys)

        if self.lang:
            action_completed_q = action_completed_q.filter(ExperimentAction.metadata_json["lang"] == self.lang)

        # only operate on the thankees that have a thank but not a survey
        action_completed = action_completed_q.order_by(desc(ExperimentAction.created_dt)).all()
        action_completed_needing_survey = [(expActionThank, expThing, expActionSurvey) for
                                           (expActionThank, expThing, expActionSurvey)
                                           in action_completed if not expActionSurvey]
        action_completed_with_survey = [(expActionThank, expThing, expActionSurvey) for
                                        (expActionThank, expThing, expActionSurvey)
                                        in action_completed if expActionSurvey]
        logging.info(
            f'There are {len(action_completed_needing_survey)} experimentActions with thanks but without survey')
        logging.info(f'There are {len(action_completed_with_survey)} experimentActions with thanks and with survey')
        for th in action_completed_with_survey:
            logging.debug(f'thanked_thankee_with_survey: {th[0].id, th[1].id, th[2].id}')

    def dedupe(self):
        # make sure the thankees are unique to avoid sending messages
        thankees_needing_survey_experiment_action = []
        seen_thankees = set()
        return seen_thankees



def fr_wiki_welcome_pilot_survey(db, batch_size, lang, intervention_name, intervention_type, config):
    afus = ActionFollowUpSurvey(db, batch_size, lang, intervention_name, intervention_type, config)
    return afus.run()
