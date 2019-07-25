import datetime
import os
import time

import mwapi as mwapi
import mwoauth as mwoauth
from requests_oauthlib import OAuth1
from sqlalchemy import or_, func, desc
import sqlalchemy
import civilservant.logs
from civilservant.util import PlatformType, ThingType
from sqlalchemy.orm.attributes import flag_modified

civilservant.logs.initialize()
import logging
from civilservant.db import init_session
from civilservant.models.core import ExperimentAction, OAuthUser


class thanksSender():
    """
    mostly acts on the metadata_json field. Field data codes
    - thanks_sent:
       - key doesnt exist --> not yet tried or error sending
       - True --> successfully sent
       - False --> cannot be sent for some reason
    - errors:
       - key doesn't exist --> not yet tried or success on first time
       - list of dicts --> {dt: errorstr}
    """
    def __init__(self, thank_batch_size=1):
        self.thank_batch_size = os.getenv('CS_WIKIPEDIA_OAUTH_BATCH_SIZE', thank_batch_size)
        logging.info(f"Thanking batch size set to : {self.thank_batch_size}")
        self.db_session = init_session()

    def find_thanks_needing_send(self, lang):
        """
        process: find all thanks that are:
        0. an experiment action with id=-1 and type=thanks
        1. not yet sent
        2. limit batch size
        3. in reverse chronological order (FIFO)
        3. matching lang
        5. select for update
        :return: list of thanks_to_send
        """
        # TODO lang is not in here yet
        thanks_needing = self.db_session.query(ExperimentAction) \
            .filter(ExperimentAction.experiment_id == -1) \
            .filter(ExperimentAction.action == 'thank') \
            .filter(ExperimentAction.metadata_json['thanks_sent'] == None) \
            .filter(ExperimentAction.metadata_json["lang"]==lang) \
            .order_by(desc(ExperimentAction.created_dt)) \
            .limit(self.thank_batch_size).all()
        logging.info(f"Found {len(thanks_needing)} thanks needing sending.")
        return thanks_needing

    def try_send_thanks(self, lang, experiment_action):
        """
        States that thanks Experiment acitons ought to be in: by metadata_json dict.
        1. Never attempted --> no such key
        2. Sucessful --> "thanks_sent"=true
        3. Error ---> "thanks_sent"=false "errors":["list of error dicts"]
        :return: count of thanks sent
        """
        if not experiment_action.metadata_json:
            experiment_action.metadata_json = {"thanks_sent":None, "errors":[]}

        prev_errors = experiment_action.metadata_json['errors'] if "errors" in experiment_action.metadata_json else []

        try:
            # send thanks
            thank_response = self.actually_post_thanks(lang, experiment_action)
            experiment_action.metadata_json['thanks_sent'] = True
            experiment_action.metadata_json['thanks_response'] = thank_response
            experiment_action.metadata_json['errors'] = prev_errors
        except Exception as e:
            # network error
            logging.exception(f"Error sending thanks: {e}")
            next_error = {str(datetime.datetime.utcnow()): str(e)}
            total_errors = prev_errors + [next_error]
            experiment_action.metadata_json['errors'] = total_errors
            if isinstance(e, mwapi.errors.APIError):
                if e.code in ['invalidrecipient']:
                    experiment_action.metadata_json['thanks_sent'] = False

        finally:
            # assert either sucess or extra error.
            sucessfully_sent = experiment_action.metadata_json['thanks_sent'] == True if "thanks_sent" in experiment_action.metadata_json else False
            correct_error_count = len(prev_errors) + 1 == len(experiment_action.metadata_json["errors"]) if "errors" in experiment_action.metadata_json else True
            assert sucessfully_sent or correct_error_count, "neither success nor extra error recorded"

    def actually_post_thanks(self, lang, experiment_action):
        """There are 3 different tokens to get straight here:
        1. The consumer token which verifies the application
        2. The access token which verifies the user login
        3. The CSRF token which verifies the intent to send a thank.
        """

        # Construct an auth object with the consumer and access tokens
        consumer_token = mwoauth.ConsumerToken(
            os.environ['CS_OAUTH_CONSUMER_KEY'],
            os.environ['CS_OAUTH_CONSUMER_SECRET'])

        # TODO reconstruct the JWT, Epenn why are access_token['key'] and ['secret'] not stored?
        # oauth_user = self.db_session.query(OAuthUser).filter(OAuthUser.id == experiment_action.action_key_id) \
        #     .one()
        # access_token = oauth_user.access_token_json


        # This copied from:
        # https://github.com/mediawiki-utilities/python-mwapi/blob/master/demo_mwoauth.py
        auth1 = OAuth1(client_key=consumer_token.key,
                       client_secret=consumer_token.secret,
                       resource_owner_key='7729349ded39da410006ad7dd87e48f6',
                       resource_owner_secret='217b890e5ea10286db6140bf068494ec526b2502')
                # Construct an mwapi session.  Nothing special here.
        session = mwapi.Session(
            host="https://en.wikipedia.org",
            user_agent="Gratitude prototyping session - max@civilservant.io")
                # Get the CSRF token
        csrf_response = session.get(action='query', meta='tokens', format='json', type='csrf', auth=auth1)
        csrf_token = csrf_response['query']['tokens']['csrftoken']
        logging.debug(f"CSRF TOKEN WORKING EDITION IS: {csrf_token}")
        rev_id_to_thank = int(experiment_action.action_object_id)
        logging.info(f"rev id to thank is: {rev_id_to_thank}")
        thank_response = session.post(action='thank', rev=rev_id_to_thank, token=csrf_token, source='app', auth=auth1)


        if "result" in thank_response:
            if "success" in thank_response["result"]:
                if thank_response['result']['success']:
                    return thank_response
                else:
                    raise ValueError(f"non success code {thank_response['result']['success']}")
            else:
                raise ValueError(thank_response["result"])
        else:
            raise ValueError("no results key in response")


    def update_action_status(self, experiment_action):
        logging.debug(f"In update status with metadata {experiment_action.metadata_json}")

        flag_modified(experiment_action, "metadata_json")
        self.db_session.add(experiment_action)
        self.db_session.commit()
        # except:
        #     self.db_session.rollback()

    def run(self, langs=['en']):
        for lang in langs:
            actions_needing = self.find_thanks_needing_send(lang)
            for action in actions_needing:
                self.try_send_thanks(lang, action)
                self.update_action_status(action)


if __name__ == "__main__":
    ts = thanksSender()
    ts.run()
