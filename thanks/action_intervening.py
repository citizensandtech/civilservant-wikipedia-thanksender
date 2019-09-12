import datetime
import os
import sqlalchemy

from civilservant.models.core import ExperimentAction
from civilservant.util import PlatformType, ThingType
from civilservant.wikipedia.actions.message import send_talkpage_message

import civilservant.logs
civilservant.logs.initialize()
import logging


def get_template_and_fill(action, intervention_name):
    lang = action.metadata_json['lang']
    template_base_dir = os.environ['CS_WIKIPEDIA_TEMPLATE_DIR']
    template_dir = os.path.join(template_base_dir, intervention_name)
    templates = os.listdir(template_dir)
    template_lang_f = [templ for templ in templates if templ.startswith(lang)][0]
    template_lang = None
    with open(os.path.join(template_dir,template_lang_f),'r') as f:
        template_lang = f.read()
    try:
        template_lang_filled = template_lang.format(**action.metadata_json)
        return template_lang_filled
    except KeyError as e:
        raise ValueError(f'Couldnt fill template {template_lang_f} with dict {action.metadata_json}. Exact error was: {e}')

def attempt_talk_page_message(action, intervention_name, intervention_type, api_con, dry_run):
    page_text = get_template_and_fill(action, intervention_name)

    post_success, reason = send_talkpage_message(user_name=action.action_object_id,
                                                 lang=action.metadata_json['lang'],
                                                 post_text=page_text,
                                                 mwapi_session=None,
                                                 auth=None,
                                                 skip_words=[],
                                                 dry_run=dry_run,
                                                 check_blocked=True)

    return post_success, reason


def attempt_action(action, intervention_name, intervention_type, api_con, dry_run):
    """
    :param api_con: a dict of apis connections to make use of
    :param dry_run: flag on whether this is a dry run
    :param db: database connection
    :param logging: logger
    :param batch_size:
    :param intervention_name:
    :param intervention_type:
    :return: list of experiment actions
    """
    intervention_type_fn = {'talk_page_message': attempt_talk_page_message}

    try:
        return intervention_type_fn[intervention_type](action, intervention_name, intervention_type, api_con, dry_run)
    except KeyError as e:
        logging.info(f'No intervening logic defined for intervention: {intervention_type}. {e}')
        raise
    except ValueError as e:
        raise
