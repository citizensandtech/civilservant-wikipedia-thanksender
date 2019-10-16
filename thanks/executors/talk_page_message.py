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
    template_dir_summary = os.path.join(template_base_dir, intervention_name + '_summary')
    templates = os.listdir(template_dir)
    templates_summary = os.listdir(template_dir_summary)
    template_lang_f = [templ for templ in templates if templ.startswith(lang)][0]
    template_lang_f_summary = [templ for templ in templates_summary if templ.startswith(lang)][0]

    # first try and fill the template
    with open(os.path.join(template_dir, template_lang_f), 'r') as f:
        template_lang = f.read()
    try:
        template_lang_filled = template_lang.format(**action.metadata_json)
    except KeyError as e:
        raise ValueError(
            f'Couldnt fill template {template_lang_f} with dict {action.metadata_json}. Exact error was: {e}')

    # second try and fill the summary
    with open(os.path.join(template_dir_summary, template_lang_f_summary), 'r') as f:
        template_lang_summary = f.read()
    try:
        template_lang_summary_filled = template_lang_summary.format(**action.metadata_json)
    except KeyError as e:
        raise ValueError(
            f'Couldnt fill template {template_lang_f} with dict {action.metadata_json}. Exact error was: {e}')
    except FileNotFoundError as e:
        logging.debug(f'Could not find file {e}. Going to rely on Wikipedia to make autogenerated summaries instead')
        template_lang_summary_filled = None

    return template_lang_filled, template_lang_summary_filled


def talk_page_message(action, intervention_name, intervention_type, api_con, dry_run, config):
    """
    for use with ExperimentActionController's execution phase
    :param action:
    :param intervention_name:
    :param intervention_type:
    :param api_con:
    :param dry_run:
    :return:
    """
    page_text, summary = get_template_and_fill(action, intervention_name)

    user_name = action.action_object_id
    # user name was historically held in this field until WikipediaUsers Table came along,
    # so make it backwards compatible
    if 'user_name' in action.metadata_json:
        user_name = action.metadata_json['user_name']
    post_success, reason = send_talkpage_message(user_name=user_name,
                                                 lang=action.metadata_json['lang'],
                                                 post_text=page_text,
                                                 mwapi_session=None,
                                                 auth=None,
                                                 skip_words=config['message_settings']['skip_words'],
                                                 dry_run=dry_run,
                                                 check_blocked=config['message_settings']['check_blocked'],
                                                 check_uncreated=config['message_settings']['check_uncreated'],
                                                 section=config['message_settings']['seciton'],
                                                 summary=summary)

    return post_success, reason
