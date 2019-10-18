import math
import random

from civilservant.wikipedia.connections.api import get_mwapi_session, get_auth
from civilservant.wikipedia.queries.sites import get_new_users, get_volunteer_signing_users
from civilservant.models.core import Experiment, ExperimentThing, ExperimentAction
from civilservant.models.wikipedia import WikipediaUser
from civilservant.util import ThingType, PlatformType

import civilservant.logs
from sqlalchemy import func, desc

civilservant.logs.initialize()
import logging


def welcome(db, batch_size, lang, intervention_name, intervention_type, config):
    """
    :param db:  connection to make use of
    :param batch_size:
    :param lang:
    :param intervention_name:
    :param intervention_type:
    :return: new_actions a list of orm objects of added users, continuation information
    """
    mwapi_session = get_mwapi_session(lang=lang)

    auth = get_auth()

    experiment_id = _get_experiment_id(db, config['name'])

    latest_registration = _get_last_registration_of_last_onboarded_user(db, experiment_id)

    logging.info(f'Latest registration of known users are: {latest_registration}')

    new_users = get_new_users(mwapi_session, auth=auth, end_time=latest_registration)

    logging.info(f'New users polled.')

    new_known_users = [user for user in new_users if _user_exists_in_db(db, lang, user_name=user['user_name'])]

    new_unknown_users = [user for user in new_users if user not in new_known_users]

    logging.info(f'There were {len(new_known_users)} already known new users '
                 f'and {len(new_unknown_users)} unknown new users')
    assert len(new_known_users) + len(new_unknown_users) == len(new_users)

    if not new_unknown_users:
        # nobody new to report
        return []
    else:
        new_actions = []
        volunteer_signing_users = get_volunteer_signing_users(mwapi_session, lang)
        for new_unknown_user in new_unknown_users:
            wikipedia_user, experiment_thing, experiment_action = _create_new_user(db, lang, new_unknown_user,
                                                                                   intervention_name,
                                                                                   intervention_type,
                                                                                   config, volunteer_signing_users)
            # there should always be a wikipedia user to save
            db.add(wikipedia_user)
            # if they had the right creation type they'd have an ET and an EA
            if experiment_thing:
                db.add(experiment_thing)
            if experiment_action:
                db.add(experiment_action)
                new_actions.append(experiment_action)
            db.commit()
        return new_actions


def _user_exists_in_db(db, lang, user_name):
    """
    check that user exists in the db
    :param db:
    :param lang:
    :param user_name:
    :return:
    """
    user_q = db.query(WikipediaUser).filter_by(lang=lang, user_name=user_name)
    db_users = user_q.all()
    if len(db_users) > 1:
        logging.error('Found more than 1 already existing Wikipedia User. Something went wrong wrong.')
    # TODO check that ET also exists and raise assertion error if not
    return True if len(db_users) > 0 else False


def _create_new_user(db, lang, new_user, intervention_name, intervention_type, config, volunteer_signing_users):
    """
    create a wikipediaUser object, and if their creation_type is correct also create experimentThings and experimentAction
    :param db:
    :param lang:
    :param new_user:
    :param intervention_name:
    :param intervention_type:
    :param config:
    :param volunteer_signing_users:
    :return:
    """

    # 0. create a wikipedia user
    creation_type = new_user['action']
    wikipedia_user = WikipediaUser(lang=lang,
                                   user_name=new_user['user_name'],
                                   user_id=new_user['user_id'],
                                   user_registration=new_user['user_registration'],
                                   metadata_json={'creation_type': creation_type})

    # db.add(wikipedia_user)
    # db.commit()
    # check if the creation_type is desired. this is for compatibility with pywikibot's welcome.py
    # there are 4 creation types: create, create2, autocreate, byemail
    # https://www.mediawiki.org/wiki/Manual:User_creation
    logging.debug(f'Created WikipediaUser {wikipedia_user.user_name}, with creation_type {creation_type}')
    if creation_type in ['create', 'autocreate']:
        return _create_experiment_thing_actions(db, lang, wikipedia_user, intervention_name, intervention_type, config,
                                                volunteer_signing_users)
    else:
        return wikipedia_user, None, None


def _create_experiment_thing_actions(db, lang, wikipedia_user, intervention_name, intervention_type, config,
                                     volunteer_signing_users):
    # get the wikipediaUser id back
    wu_id = wikipedia_user.id
    # 1. get their randomization
    experiment_name = config['name']
    experiment_id = _get_experiment_id(db, experiment_name)
    randomization_arm, randomization_block_id, randomization_index = _get_next_randomization_arm(db, experiment_id,
                                                                                                 config)
    randomization_arm_obfuscated = _obfuscated_randomization_arm(db, experiment_id, randomization_arm)
    # 2. store the randomizaiton and user in an ET.
    wu_sync_object = wikipedia_user.to_json()

    experiment_thing = ExperimentThing(id=f'user:{lang}:{wikipedia_user.user_name}',
                                       thing_id=wu_id,
                                       experiment_id=experiment_id,
                                       object_type=ThingType.WIKIPEDIA_USER,
                                       object_platform=PlatformType.WIKIPEDIA,
                                       randomization_arm=randomization_arm,
                                       randomization_condition='welcome',
                                       metadata_json={"randomization_block_id": randomization_block_id,
                                                      "randomization_index": randomization_index,
                                                      "sync_object":wu_sync_object})
    # 3. create an action based on the randomization and user, and new mentor.
    signer = random.choice(volunteer_signing_users)

    experiment_action = ExperimentAction(experiment_id=experiment_id,
                                         action_object_id=wu_id,
                                         action_object_type=ThingType.WIKIPEDIA_USER,
                                         action_subject_id=intervention_name,
                                         action_subject_type=intervention_type,
                                         action_platform=PlatformType.WIKIPEDIA,
                                         action_key_id=randomization_arm,
                                         action=intervention_type,
                                         metadata_json={"randomization_arm": randomization_arm,
                                                        "randomization_arm_obfuscated": randomization_arm_obfuscated,
                                                        "signer": signer,
                                                        "lang": lang,
                                                        "user_name": wikipedia_user.user_name})
    return wikipedia_user, experiment_thing, experiment_action


def _get_experiment_id(db, experiment_name):
    return db.query(Experiment.id).filter_by(name=experiment_name).one()


def _get_num_experiment_things(db, experiment_id):
    return db.query(ExperimentThing).filter_by(experiment_id=experiment_id).count()


def _get_next_randomization_arm(db, experiment_id, config):
    num_experiment_things = _get_num_experiment_things(db, experiment_id)
    logging.info(f'Already have {num_experiment_things} experiment things in study')
    experiment = db.query(Experiment).filter_by(id=experiment_id).one()
    randomizations = experiment.settings_json['randomizations']['data']
    randomziation_arm, randomization_block_id = randomizations[num_experiment_things]
    units_per_block = config['settings']['units_per_block']
    expected_block_id = math.floor(num_experiment_things / units_per_block)
    expected_block_id = expected_block_id + 1  # switched to R generation method which is 1-indexed
    logging.debug(f'''Correct block calculation num_experiment_things:{num_experiment_things} 
    units_per_block:{units_per_block} expected_block_id:{expected_block_id} actual_block_id:{randomization_block_id}''')
    assert expected_block_id == randomization_block_id

    return randomziation_arm, randomization_block_id, num_experiment_things


def _obfuscated_randomization_arm(db, experiment_id, randomization_arm):
    experiment = db.query(Experiment).filter_by(id=experiment_id).one()
    randomization_obfuscations = experiment.settings_json['randomization_obfuscations']
    return randomization_obfuscations[str(randomization_arm)]


def _get_last_registration_of_last_onboarded_user(db, experiment_id):
    latest_et = db.query(ExperimentThing).filter_by(experiment_id=experiment_id) \
        .order_by(desc(ExperimentThing.created_dt)).limit(1).one_or_none()
    return latest_et.created_dt if latest_et else None
