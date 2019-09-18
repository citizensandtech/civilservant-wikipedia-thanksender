import datetime
import os
import time
from operator import and_

import mwapi as mwapi
import mwoauth as mwoauth
from requests_oauthlib import OAuth1
from sqlalchemy import and_, or_, func, desc
import sqlalchemy
from civilservant.util import PlatformType, ThingType
from thanks.utils import update_action_status, MaxInterventionAttemptsExceededError

import civilservant.logs
civilservant.logs.initialize()
import logging
from civilservant.db import init_session
from civilservant.models.core import ExperimentAction, OAuthUser, ExperimentThing
from thanks.action_creating import create_actions
from thanks.action_intervening import attempt_action



class ExperimentActionController(object):
    """
    This class optionally creates experimentActions, finds incomplete or unsucessful actions, and attempts to complete them.
    The ExperimentAciton metadata_json field is used to store information about the completedness of the action.
    The metadata_json field contains root keys
    - action_complete
        - key doesn't exists --> hasn't been attempted
        - None --> attempted but not successful yet
        - False --> attempted but error'd more than Max times
        - True --> action completed successfuly
    - action_data
        - optional data about the actions' completion (like a return value from external api)
    - errors:
       - key doesn't exist --> not yet tried or success on first time
       - list of dicts --> {dt: errorstr} #TODO if uncaught error have a dict that contains the stracktrace etc.
    """

    def __init__(self, lang=None, dry_run=True, enable_create_actions=True,
                 enable_execute_actions=True):
        self.batch_size = int(os.getenv('CS_WIKIPEDIA_ACTION_BATCH_SIZE', 2))
        logging.info(f"Survey batch size set to : {self.batch_size}")
        self.db_session = init_session()
        self.lang = lang
        logging.info(f"Survey sending language set to. {self.lang}")
        self.consumer_token = mwoauth.ConsumerToken(
            os.environ['CS_OAUTH_CONSUMER_KEY'],
            os.environ['CS_OAUTH_CONSUMER_SECRET'])
        self.max_send_errors = int(os.getenv('CS_OAUTH_THANKS_MAX_SEND_ERRORS', 5))
        self.intervention_type = os.environ['CS_WIKIPEDIA_INTERVENTION_TYPE']
        self.intervention_name = os.environ['CS_WIKIPEDIA_INTERVENTION_NAME']
        self.api_con = None # a slot for a connection or session to keep open between different phases.
        self.dry_run = dry_run
        self.enable_create_actions = enable_create_actions
        self.enable_execute_actions = enable_execute_actions

    def create_new_actions(self):
        """
        Optional, create new actions that will be picked up later.
        Sometimes other processes may generate acitons (like users in sending gratitude).
        Other times the action needs to be created by ourselves (like sending out a survey).
        :return: list of experimentActions or None if there are no actions to be created
        """
        return create_actions(db=self.db_session,
                              batch_size=self.batch_size, lang=self.lang,
                              intervention_name=self.intervention_name,
                              intervention_type=self.intervention_type)

    def find_incomplete_actions(self):
        """
        Finds actions that need to be completed based on intervention name and type.
         0. correct interventation name and type
         1. not yet sent
         2. limit batch size
         3. in reverse chronological order (LIFO)
         3. matching self.lang if set
        :return: list of experimentActions
        """
        incomplete_actions_q = self.db_session.query(ExperimentAction) \
        .filter(and_(ExperimentAction.action_subject_id==self.intervention_name,
                ExperimentAction.action==self.intervention_type,
                ExperimentAction.metadata_json['action_complete'] == None))

        if self.lang:
            incomplete_actions_q = incomplete_actions_q.filter(ExperimentAction.metadata_json["lang"] == self.lang)

        incomplete_actions = incomplete_actions_q.order_by(desc(ExperimentAction.created_dt)) \
                            .with_for_update(skip_locked=True) \
                            .limit(self.batch_size) \
                            .all()

        # logging.debug(incomplete_actions_q)logging.info(f"Found {len(incomplete_actions)} thanks needing sending. lang is {self.lang}")
        return incomplete_actions

    def execute_actions(self, incomplete_actions):
        action_fatalities = []
        for action in incomplete_actions:
            try:
                self.db_session.refresh(action)
                self.intervene_once(action)
                update_action_status(self.db_session, logging, action)
                action_fatalities.append(False)
            except MaxInterventionAttemptsExceededError:
                logging.error(f"Found a MaxInterventionAttemptsExceededError expAction id={action.id}")
                update_action_status(self.db_session, logging, action)
                action_fatalities.append(True)
            except Exception as e:
                logging.error(f"Outer loop is catching {e}")
                action_fatalities.append(True)
                self.db_session.rollback()
        return action_fatalities

    def intervene_once(self, experiment_action):
        """
        States that survey Experiment acitons ought to be in: by metadata_json dict.
        1. Never attempted --> no such key
        2. Sucessful --> "action_complete"=true
        3. Error ---> "action_complete"=false "errors":["list of error dicts"]
        :return: count of survey sent
        """
        if not experiment_action.metadata_json:
            experiment_action.metadata_json = {"action_complete": None, "errors": []}

        prev_errors = experiment_action.metadata_json['errors'] if "errors" in experiment_action.metadata_json else []

        try:
            action_complete, action_response = attempt_action(action=experiment_action,
                                             intervention_name=self.intervention_name,
                                             intervention_type=self.intervention_type,
                                             api_con=self.api_con, dry_run=self.dry_run)
            experiment_action.metadata_json['action_complete'] = action_complete
            experiment_action.metadata_json['action_response'] = action_response
            experiment_action.metadata_json['errors'] = prev_errors
        except Exception as e:
            # network error
            logging.exception(f"Error sending thanks: {e}")
            next_error = {str(datetime.datetime.utcnow()): str(e)}
            total_errors = prev_errors + [next_error]
            experiment_action.metadata_json['errors'] = total_errors
            if isinstance(e, mwapi.errors.APIError):
                if e.code in ['invalidrecipient', 'blocked']:
                    experiment_action.metadata_json['action_complete'] = False
            logging.info(f"Total errors are: {total_errors}, max_send_errors are {self.max_send_errors}")
            if len(total_errors) > self.max_send_errors:
                experiment_action.metadata_json['action_complete'] = False
                raise MaxInterventionAttemptsExceededError
        finally:
            # assert either sucess or extra error.
            sucessfully_sent = experiment_action.metadata_json['action_complete'] == True \
                                  if "action_complete" in experiment_action.metadata_json else False
            correct_error_count = len(prev_errors) + 1 == len(experiment_action.metadata_json["errors"]) \
                                       if "errors" in experiment_action.metadata_json else True
            assert sucessfully_sent or correct_error_count, "neither success nor extra error recorded"

    def run(self):
        logging.info(f"Starting run at {datetime.datetime.utcnow()}")

        if self.enable_create_actions:
            new_actions = self.create_new_actions()
            logging.info(f'New actions created: {len(new_actions)}')

        if self.enable_execute_actions:
            incomplete_actions = self.find_incomplete_actions()
            action_fatalities = self.execute_actions(incomplete_actions)
            logging.info(f'Action fatalities were: {action_fatalities}')

        logging.info(f"Ended run at {datetime.datetime.utcnow()}")

if __name__ == "__main__":
    eac = ExperimentActionController(lang=None, dry_run=True)
    eac.run()
