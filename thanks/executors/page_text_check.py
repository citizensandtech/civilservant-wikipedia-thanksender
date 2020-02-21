import datetime
import os
import sqlalchemy

from civilservant.models.core import ExperimentAction
from civilservant.util import PlatformType, ThingType
from civilservant.wikipedia.actions.message import send_talkpage_message, get_page_text

import civilservant.logs
from civilservant.wikipedia.connections.api import get_auth, get_mwapi_session

civilservant.logs.initialize()
import logging


def page_text_check(action, intervention_name, intervention_type, api_con, dry_run, config):
    """
    for use with ExperimentActionController's execution phase
    :param action:
    :param intervention_name:
    :param intervention_type:
    :param api_con:
    :param dry_run:
    :return:
    """
    lang = action.metadata_json['lang']
    mwapi_session = get_mwapi_session(lang=lang)
    skip_words = config['message_settings']['skip_words']
    assert len(skip_words) > 0, 'There werent any skip words to check'
    auth = get_auth()

    page_title = f"User_talk:{action.metadata_json['user_name']}"
    page_text = get_page_text(page_title, mwapi_session=mwapi_session, auth=auth)


    control_not__treated = True
    reason = f'skip words {skip_words} not found in page'
    for skip_word in skip_words:
        if skip_word in page_text:
            raise ValueError(f'skip word "{skip_word}" found in page')

    return control_not__treated, reason
