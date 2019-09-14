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
from sqlalchemy.orm.util import outerjoin

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
    logging.info(f'Seeking thankees who received thanks before {thanks_latest_date}')
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
                               ExperimentAction.metadata_json['thanks_sent'] != None,
                               ExperimentAction.metadata_json['lang'] != 'en')

    relevant_surveys = and_(ExperimentActionSurvey.action_subject_id == intervention_name,
                            ExperimentActionSurvey.action == intervention_type)

    # the first join is to get
    thanked_thankees_p = db.query(ExperimentAction, ExperimentThing, ExperimentActionSurvey) \
        .join(ExperimentThing, received_thanks_onclause) \
        .filter(thanks_sent_qualify)

    thanked_thankees_q = thanked_thankees_p \
        .outerjoin(ExperimentActionSurvey, survey_sent_onclause) \
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
    for th in thanked_thankees_with_survey:
        logging.debug(f'thanked_thankee_with_survey: {th[0].id, th[1].id, th[2].id}')
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
    # thankees_needing_survey_experiment_action = thankees_needing_survey_experiment_action[:batch_size]
    # logging.info(f'There are {len(thankees_needing_survey_experiment_action)} unique thankees needing survey')

    # get the matching pairs based on the block.
    thankees_and_control_needing_survey_experiment_action = []
    for (expActionThank, expThing, expActionSurvey) in thankees_needing_survey_experiment_action:
        block_id = expThing.metadata_json["randomization_block_id"]
        block_lang = expThing.metadata_json["sync_object"]["lang"]
        logging.debug(f'Thankee {expThing.id} has block_id {block_id}')
        try:
            block_partner = db.query(ExperimentThing) \
                .filter(and_(ExperimentThing.metadata_json['randomization_block_id'] == block_id,
                        ExperimentThing.randomization_arm == 0,
                        ExperimentThing.metadata_json['sync_object']['lang'] == block_lang)).one()
        except sqlalchemy.orm.exc.NoResultFound:
            raise ValueError(f"Cannot find matching pair for thankee {expThing.metadata_json}")
        except sqlalchemy.orm.exc.MultipleResultsFound:
            raise ValueError(f"Multiple results found for block partner for {expThing.id}")
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
                                                    "user_name": expThing.metadata_json['sync_object']['user_name']})
        thankees_needing_survey_experiment_actions.append(survey_ea)

    db.add_all(thankees_needing_survey_experiment_actions)
    db.commit()

    return thankees_needing_survey_experiment_actions


def create_actions_thankees_needing_survey_fast(db, batch_size, lang, intervention_name, intervention_type):
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

    early_enough, sent_surveys = get_thanked_thankees(db, thanks_latest_date, intervention_type, intervention_name)

    thanked_thankees_without_survey, thanked_thankees_with_survey = thankees_having_survey(early_enough, sent_surveys)

    assert len(thanked_thankees_without_survey) + len(thanked_thankees_with_survey) == len(early_enough)

    logging.info(f'There are {len(early_enough)} experimentActions meeting date criteria')
    logging.info(f'There are {len(thanked_thankees_without_survey)} experimentActions with thanks but without survey')
    logging.info(f'There are {len(thanked_thankees_with_survey)} experimentActions with thanks and with survey')

    unique_thanked_thankees = uniqueify_thanked_thankees(thanked_thankees_without_survey)
    logging.info(f'There are {len(unique_thanked_thankees)} unique experimentActions with but without survey')
    unique_thanked_thankees_and_control = make_matching_partners(db, unique_thanked_thankees)
    unique_thanked_thankees_and_control_actions = make_experiment_actions(db, unique_thanked_thankees_and_control,
                                                                          intervention_name, intervention_type)
    return unique_thanked_thankees_and_control_actions


def make_matching_partners(db, thanked_thankees):
    # get the matching pairs based on the block.
    thankees_and_control = []
    for (expAction, expActionSurvey) in thanked_thankees:
        expThing = db.query(ExperimentThing) \
            .filter(and_(ExperimentThing.metadata_json['sync_object']['lang'] == expAction.metadata_json['lang'],
                         ExperimentThing.metadata_json['sync_object']['user_name'] ==
                         expAction.metadata_json['thanks_response']['result']['recipient'])
                    ).one()
        block_id = expThing.metadata_json["randomization_block_id"]
        block_lang = expThing.metadata_json["sync_object"]["lang"]
        logging.debug(f'Thankee {expThing.id} has block_id {block_id}')
        try:
            block_partner = db.query(ExperimentThing) \
                .filter(ExperimentThing.metadata_json['randomization_block_id'] == block_id,
                        ExperimentThing.randomization_arm == 0,
                        ExperimentThing.metadata_json['sync_object']['lang'] == block_lang).one()
        except sqlalchemy.orm.exc.NoResultFound:
            raise ValueError(f"Cannot find matching pair for thankee {expThing.metadata_json}")
        except sqlalchemy.orm.exc.MultipleResultsFound:
            raise ValueError(f"Multiple results found for block partner for {expThing.id}")
        thankees_and_control.append(expThing)
        thankees_and_control.append(block_partner)
    return thankees_and_control


def make_experiment_actions(db, thankees_and_control, intervention_name, intervention_type):
    thankees_needing_survey_experiment_actions = []
    for expThing in thankees_and_control:
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
                                                    "user_name": expThing.metadata_json['sync_object']['user_name']})
        thankees_needing_survey_experiment_actions.append(survey_ea)

    db.add_all(thankees_needing_survey_experiment_actions)
    db.commit()
    return thankees_needing_survey_experiment_actions


def uniqueify_thanked_thankees(thanked_thankees):
    thankee_ids_all = [
        (expAction.metadata_json['lang'], expAction.metadata_json['thanks_response']['result']['recipient']) for
        (expAction, expActionSurvey) in thanked_thankees]
    thankee_ids_uniq = list(set(thankee_ids_all))
    return [(expAction, expActionSurvey) for (expAction, expActionSurvey) in thanked_thankees
            if (expAction.metadata_json['lang'], expAction.metadata_json['thanks_response']['result']['recipient']) if
            thankee_ids_uniq]


def get_thanked_thankees(db, thanks_latest_date, intervention_type, intervention_name):
    logging.info(f'Seeking thankees who received thanks before {thanks_latest_date}')
    ExperimentActionSurvey = aliased(ExperimentAction)

    # the we make sure the action_object_id is in the survey
    survey_sent_onclause = and_(ExperimentActionSurvey.action_object_id == \
                                ExperimentAction.metadata_json['thanks_response']['result']['recipient'],
                                ExperimentActionSurvey.metadata_json['lang'] ==
                                ExperimentAction.metadata_json['lang'])

    thanks_sent_qualify = and_(ExperimentAction.experiment_id == -1,
                               ExperimentAction.action == 'thank',
                               ExperimentAction.created_dt < thanks_latest_date,
                               ExperimentAction.metadata_json['thanks_sent'] == True,
                               ExperimentAction.metadata_json['lang'] != 'en')

    relevant_surveys = or_(and_(ExperimentActionSurvey.action_subject_id == intervention_name,
                                ExperimentActionSurvey.action == intervention_type),
                           and_(ExperimentActionSurvey.action_subject_id == None,
                                ExperimentActionSurvey.action == None))

    early_enough = db.query(ExperimentAction).filter(thanks_sent_qualify).order_by(
        desc(ExperimentAction.created_dt)).all()

    sent_surveys = db.query(ExperimentActionSurvey).filter(relevant_surveys).all()

    return early_enough, sent_surveys


def thankees_having_survey(early_enough, sent_surveys):
    thanked_thankees_without_survey = []
    thanked_thankees_with_survey = []

    # stupid double-loop algo instead of left outer join, fml
    for expAction in early_enough:
        ea_lang, ea_user_name = expAction.metadata_json['lang'], expAction.metadata_json['thanks_response']['result'][
            'recipient']
        found = False
        for expActionSurv in sent_surveys:
            eas_lang, eas_user_name = expActionSurv.metadata_json['lang'], expActionSurv.action_object_id
            if (ea_lang == eas_lang) and (ea_user_name == eas_user_name):
                # match
                found = expActionSurv
        # ive now search through all the surveys
        if found:
            thanked_thankees_with_survey.append((expAction, found))
        else:
            thanked_thankees_without_survey.append((expAction, None))

    return thanked_thankees_without_survey, thanked_thankees_with_survey

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
    intervention_name_fn = {'gratitude_thankee_survey': create_actions_thankees_needing_survey_fast}

    try:
        creation_fn = intervention_name_fn[intervention_name]
    except KeyError as e:
        logging.info(f'No creation logic defined for intervention: {intervention_name}, error was {e}')
        return None
    return creation_fn(db, batch_size, lang, intervention_name,
                       intervention_type)
