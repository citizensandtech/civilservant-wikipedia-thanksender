import datetime
from civilservant.models.core import ExperimentThing, ExperimentAction
import civilservant.logs
from sqlalchemy import desc

from thanks.utils import _get_experiment_id, LikelyDataError, ImplausibleNoRecentRegistrationsError, \
    LikelyActionCompletionError

civilservant.logs.initialize()
import logging


def post_creation_validators(db, config):
    # TODO rewrite as subclass of experimentValidator
    """
    make sure that the creation stage went as planned.
    :param db:
    :return: has no return value just will raise errors by logging ERROR or CRITICAL
    """
    experiment_id = _get_experiment_id(db, config['name'])
    now = datetime.datetime.utcnow()
    # 0. There was an ET in the last hour.
    hour_ago = now - datetime.timedelta(hours=1)
    last_hour_ets = db.query(ExperimentThing) \
        .filter(ExperimentThing.experiment_id == experiment_id) \
        .filter(ExperimentThing.created_dt >= hour_ago).all()

    if len(last_hour_ets) == 0:
        logging.critical(f'There were no ETs created in the last hour (since {hour_ago})')
        # raise ImplausibleNoRecentRegistrationsError
    else:
        logging.info('There were ETs created in the last hour.')

    # 1. Every recent ET has an EA.
    #TODO: implement this validation.

def post_execution_validators(db, config):
    # 0. most 10 recent EAs are >50% action completed=TRUE
    experiment_id = _get_experiment_id(db, config['name'])
    num_recent = 10
    frac_threshhold = 0.5
    recent_eas_q = db.query(ExperimentAction) \
        .filter(ExperimentAction.experiment_id == experiment_id) \
        .order_by(desc(ExperimentAction.created_dt))
    recent_eas = recent_eas_q.limit(num_recent).all()
    recent_completed_eas = [ea for ea in recent_eas if 'action_complete' in ea.metadata_json]
    recent_completed_true_eas = [ea for ea in recent_completed_eas if ea.metadata_json['action_complete'] == True]
    frac_complete = len(recent_completed_true_eas) / num_recent
    if frac_complete < frac_threshhold:
        logging.critical(f'Only {frac_complete} proportion of last {num_recent} ExperimentActions were completed successfully.')
        # raise LikelyActionCompletionError
    else:
        logging.info(f'Good. {frac_complete} of last {num_recent} ExperimentActions were completed successfully.')

    # 1. no more than 10 action_completed is NULL
    null_eas = db.query(ExperimentAction) \
        .filter(ExperimentAction.experiment_id == experiment_id) \
        .filter(ExperimentAction.metadata_json['action_complete'] == None).all()
    if len(null_eas) > 10:
        logging.critical(f'Actions dont seem to be executing fast enough. There are still {len(null_eas)} Null Experiment Actions.')
        # raise LikelyActionCompletionError
    else:
        logging.info(f'There is no large action completion backlog')
