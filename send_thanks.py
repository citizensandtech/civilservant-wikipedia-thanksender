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
    def __init__(self):
        self.thank_batch_size = os.getenv('CS_WIKIPEDIA_OAUTH_BATCH_SIZE', 2)
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
            .filter(or_(ExperimentAction.metadata_json['thanks_sent'] == None,
                        ExperimentAction.metadata_json['thanks_sent'] == False)) \
            .order_by(desc(ExperimentAction.created_dt)) \
            .limit(self.thank_batch_size).all()
        logging.info(f"Found {len(thanks_needing)} thanks needing sending.")
        return thanks_needing

    def try_send_thanks(self, lang, experimentAction):
        """
        States that thanks Experiment acitons ought to be in: by metadata_json dict.
        1. Never attempted --> no such key
        2. Sucessful --> "thanks_sent"=true
        3. Error ---> "thanks_sent"=false "errors":["list of error dicts"]
        :return: count of thanks sent
        """
        prev_errors = experimentAction.metadata_json['errors'] if 'errors' in experimentAction.metadata_json else []
        try:
            # send thanks
            self.actually_post_thanks(lang, experimentAction)
        except Exception as e:
            # network error
            next_error = {datetime.datetime.utcnow(): str(e)}
            total_errors = prev_errors.append(next_error)
            experimentAction.metadata_json['errors'] = total_errors
        finally:
            # assert either sucess or extra error.
            sucessfully_sent = experimentAction.metadata_json['thanks_sent'] == True
            final_errors = experimentAction.metadata_json['error']
            assert sucessfully_sent or (
                        len(prev_errors) + 1 == len(final_errors)), "neither success nor extra error recorded"

    def actually_post_thanks(self, lang, experimentAction):
        """There are 3 different tokens to get straight here:
        1. The consumer token which verifies the application
        2. The access token which verifies the user login
        3. The CSRF token which verifies the intent to send a thank.
        """

        # Construct an auth object with the consumer and access tokens
        consumer_token = mwoauth.ConsumerToken(
            os.environ['CS_WIKIPEDIA_OAUTH_CONSUMER_KEY'],
            os.environ['CS_WIKIPEDIA_OAUTH_CONSUMER_SECRET'])

        # TODO reconstruct the JWT, Epenn why are access_token['key'] and ['secret'] not stored?
        oauth_user = self.db_session.query(OAuthUser).filter(OAuthUser.id == experimentAction.action_key_id) \
            .one()
        access_token = oauth_user.access_token_json

        # This copied from:
        # https://github.com/mediawiki-utilities/python-mwapi/blob/master/demo_mwoauth.py

        auth1 = OAuth1(consumer_token.key,
                       client_secret=consumer_token.secret,
                       resource_owner_key=access_token['key'],
                       resource_owner_secret=access_token['secret'])

        # Construct an mwapi session.  Nothing special here.
        # In general should probably be done outside of the route function, here for simplicity.
        session = mwapi.Session(
            host=f"https://{lang}.wikipedia.org",
            user_agent="Gratitude prototyping session - max@civilservant.io")

        # Get the CSRF token
        csrf_response = session.get(action='query', meta='tokens', format='json', type='csrf', auth=auth1)
        csrf_token = csrf_response['query']['tokens']['csrftoken']

        rev_id_to_thank = experimentAction.action_object_id  # You want to change this unless you really like me creating an account.
        # Now, accessing the API on behalf of a user
        logging.info(f"About to thank rev {rev_id_to_thank} from {oauth_user.username}")
        thank_response = session.post(action='thank', rev=rev_id_to_thank, token=csrf_token, source='app', auth=auth1)

        if "result" in thank_response:
            if "success" in thank_response["result"]:
                return True
            else:
                raise ValueError(thank_response["result"])
        else:
            raise ValueError("no results key in response")
        # Looks like:
        # {'result': {'success': 1, 'recipient': 'Maximilianklein(CS)'}}

    def update_thanks_status(self, experimentAction):
        try:
            flag_modified(experimentAction.metadata_json)
            self.db_session.add(experimentAction)
            self.db_session.commit()
        except:
            self.db_session.rollback()

    def run(self, langs=['en']):
        for lang in langs:
            thanks_needing = self.find_thanks_needing_send(lang)
            for thank in thanks_needing:
                print(thank.created_dt)


if __name__ == "__main__":
    ts = thanksSender()
    ts.run()
