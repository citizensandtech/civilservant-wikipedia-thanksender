import datetime
import os
import sqlalchemy

from civilservant.models.core import ExperimentAction, ExperimentThing
from civilservant.util import PlatformType, ThingType
import civilservant.logs
civilservant.logs.initialize()
import logging

from sqlalchemy import and_, desc, or_
from sqlalchemy.orm import aliased

from uuid import uuid4



def create_actions_thankees_needing_survey(db, batch_size, lang, intervention_name, intervention_type):
    """
     process: find all survey that are:
     0. have been thanked more than 42 days ago
     1. filter out the user who have already been surveyed
     2. get the matching pairs based on block id.
     3. create experimentActions for surveysend. make the metadata_json field contain the keys you want the survey templates
        to be filled with
    """
    survey_after_days = int(os.environ['CS_WIKIPEDIA_SURVEY_AFTER_DAYS'])
    now = datetime.datetime.utcnow()
    thanks_latest_date = now - datetime.timedelta(days=survey_after_days)

    ExperimentActionSurvey = aliased(ExperimentAction)

    received_thanks_onclause = and_(ExperimentAction.metadata_json['thanks_response']['result']['recipient'] == \
                                    ExperimentThing.metadata_json['sync_object']['user_name'],
                                    ExperimentAction.metadata_json['lang'] ==
                                    ExperimentThing.metadata_json['sync_object']['lang'])

    # the we make sure the action_object_id is in the survey
    survey_sent_onclause = and_(ExperimentActionSurvey.action_object_id == \
                                ExperimentAction.metadata_json['thanks_response']['result']['recipient'],
                                ExperimentActionSurvey.metadata_json['lang'] ==
                                ExperimentAction.metadata_json['lang'])

    thanks_sent_qualify = and_(ExperimentAction.experiment_id == -1,
                               ExperimentAction.action == 'thank',
                               ExperimentAction.created_dt < thanks_latest_date,
                               ExperimentAction.metadata_json['thanks_sent'] != None)

    relevant_surveys = or_(ExperimentActionSurvey.action_subject_id == intervention_name,
                           ExperimentActionSurvey.action_subject_id == None)

    # the first join is to get
    thanked_thankees_q = db.query(ExperimentAction, ExperimentThing, ExperimentActionSurvey) \
        .join(ExperimentThing, received_thanks_onclause) \
        .outerjoin(ExperimentActionSurvey, survey_sent_onclause) \
        .filter(thanks_sent_qualify) \
        .filter(relevant_surveys)

    if lang:
        thanked_thankees_q = thanked_thankees_q.filter(ExperimentAction.metadata_json["lang"] == lang)

    # only operate on the thankees that have a thank but not a survey
    thanked_thankees = thanked_thankees_q.order_by(desc(ExperimentAction.created_dt)).all()
    thanked_thankees_needing_survey = [(expActionThank, expThing, expActionSurvey) for
                                       (expActionThank, expThing, expActionSurvey)
                                       in thanked_thankees if not expActionSurvey]
    thanked_thankees_with_survey = [(expActionThank, expThing, expActionSurvey) for
                                    (expActionThank, expThing, expActionSurvey)
                                    in thanked_thankees if expActionSurvey]
    logging.info(f'There are {len(thanked_thankees_needing_survey)} experimentActions with thanks but without survey')
    logging.info(f'There are {len(thanked_thankees_with_survey)} experimentActions with thanks and with survey')

    # make sure the thankees are unique to avoid sending messages
    thankees_needing_survey_experiment_action = []
    seen_thankees = set()
    for (expActionThank, expThing, expActionSurvey) in thanked_thankees_needing_survey:
        user_name_lang = expActionThank.metadata_json['thanks_response']['result']['recipient'], \
                         expActionThank.metadata_json['lang']
        if user_name_lang not in seen_thankees:
            thankees_needing_survey_experiment_action.append((expActionThank, expThing, expActionSurvey))
            seen_thankees.add(user_name_lang)
        else:
            continue

    # trim out list down to batch size
    thankees_needing_survey_experiment_action = thankees_needing_survey_experiment_action[:batch_size]
    logging.info(f'There are {len(thankees_needing_survey_experiment_action)} unique thankees needing survey')

    # get the matching pairs based on the block.
    thankees_and_control_needing_survey_experiment_action = []
    for (expActionThank, expThing, expActionSurvey) in thankees_needing_survey_experiment_action:
        block_id = expThing.metadata_json["randomization_block_id"]
        logging.debug(f'Thankee {expThing.id} has block_id {block_id}')
        try:
            block_partner = db.query(ExperimentThing) \
                .filter(ExperimentThing.metadata_json['randomization_block_id'] == block_id,
                        ExperimentThing.randomization_arm == 0).one()
        except sqlalchemy.orm.exc.NoResultFound:
            raise ValueError(f"Cannot find matching pair for thankee {expThing.metadata_json}")
        thankees_and_control_needing_survey_experiment_action.append(expThing)
        thankees_and_control_needing_survey_experiment_action.append(block_partner)

    thankees_needing_survey_experiment_actions = []
    for expThing in thankees_and_control_needing_survey_experiment_action:
        survey_ea = ExperimentAction(experiment_id=-3,
                                     action_object_id=expThing.metadata_json['sync_object']['user_name'],
                                     action_object_type=ThingType.WIKIPEDIA_USER,
                                     action_subject_id=intervention_name,
                                     action_subject_type=None,
                                     action_platform=PlatformType.WIKIPEDIA,
                                     action_key_id=None,
                                     action=intervention_type,
                                     metadata_json={"lang": expThing.metadata_json['sync_object']['lang'],
                                                    "anonymized_id": str(uuid4()),
                                                    "user_name":expThing.metadata_json['sync_object']['user_name']})
        thankees_needing_survey_experiment_actions.append(survey_ea)

    db.add_all(thankees_needing_survey_experiment_actions)
    db.commit()

    return thankees_needing_survey_experiment_actions


def create_actions(db, batch_size, lang, intervention_name, intervention_type):
    """
    :param db: database connection
    :param logging: logger
    :param batch_size:
    :param lang:
    :param intervention_name:
    :param intervention_type:
    :return: list of experiment actions
    """
    intervention_name_fn = {'gratitude_thankee_survey': create_actions_thankees_needing_survey}

    try:
        return intervention_name_fn[intervention_name](db, batch_size, lang, intervention_name,
                                                       intervention_type)
    except KeyError:
        logging.info(f'No logic defined for intervention: {intervention_name}')
        return None
