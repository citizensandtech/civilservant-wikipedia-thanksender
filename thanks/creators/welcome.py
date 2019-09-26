import math
import random

from civilservant.wikipedia.connections.api import get_mwapi_session
from civilservant.wikipedia.queries.sites import get_new_users, get_volunteer_signing_users
from civilservant.models.core import Experiment, ExperimentThing, ExperimentAction
from civilservant.models.wikipedia import WikipediaUser
from civilservant.util import ThingType, PlatformType

import civilservant.logs
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

    new_users, continuation = get_new_users(mwapi_session)

    new_known_users = [user for user in new_users if _user_exists_in_db(db, lang, user_name=user['user_name'])]

    new_unknown_users = [user for user in new_users if user not in new_known_users]

    logging.info(f'There were {len(new_known_users)} already known new users '
                 f'and {len(new_unknown_users)} unknown new users')
    assert len(new_known_users) + len(new_unknown_users) == len(new_users)

    if not new_unknown_users:
        #nobody new to report
        return []
    else:
        new_actions = []
        volunteer_signing_users = get_volunteer_signing_users(mwapi_session, lang)
        for new_unknown_user in new_unknown_users:

            wikipedia_user, experiment_thing, experiment_action = _create_new_user(db, lang, new_unknown_user,
                                                                                   intervention_name,
                                                                                    intervention_type,
                                                                                   config, volunteer_signing_users)
            db.add(wikipedia_user) # may already be done
            db.add(experiment_thing)
            db.add(experiment_action)
            db.commit()
            new_actions.append(experiment_action)
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
    db_user = user_q.one_or_none()
    #TODO check that ET also exists and raise assertion error if not
    return True if db_user else False

def _create_new_user(db, lang, new_user, intervention_name, intervention_type, config, volunteer_signing_users):
    # 0. create a wikipedia user
    wikipedia_user = WikipediaUser(lang=lang,
                  user_name=new_user['user_name'],
                  user_id=new_user['user_id'],
                  user_registration=new_user['user_registration'])
    # get the wikipediaUser id back
    db.add(wikipedia_user)
    db.commit()
    wu_id = wikipedia_user.id
    # 1. get their randomization
    experiment_name = config['name']
    experiment_id = _get_experiment_id(db, experiment_name)
    randomization_arm, randomization_block_id = _get_next_randomization_arm(db, experiment_id, config)
    # 2. store the randomizaiton and user in an ET.
    experiment_thing = ExperimentThing(id=f'user:{lang}:{wikipedia_user.user_name}',
                                       thing_id=wu_id,
                                       experiment_id=experiment_id,
                                       object_type=ThingType.WIKIPEDIA_USER,
                                       object_platform=PlatformType.WIKIPEDIA,
                                       randomization_arm=randomization_arm,
                                       randomization_condition='fr_wiki_welcome',
                                       metadata_json={"randomization_block_id":randomization_block_id})
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
                                     metadata_json={"randomization_arm":randomization_arm,
                                                    "signer":signer,
                                                    "lang":lang})
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
    expected_block_id  = math.floor(num_experiment_things / units_per_block)
    logging.debug(f'''Correct block calculation num_experiment_things:{num_experiment_things} 
    units_per_block:{units_per_block} expected_block_id:{expected_block_id} actual_block_id:{randomization_block_id}''')
    assert expected_block_id==randomization_block_id

    return randomziation_arm, randomization_block_id,
