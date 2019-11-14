from civilservant.models.core import Experiment
from sqlalchemy.orm.attributes import flag_modified


def update_action_status(db_session, logging, experiment_action):
    logging.debug(f"In update status with metadata {experiment_action.metadata_json}")
    flag_modified(experiment_action, "metadata_json")
    db_session.add(experiment_action)
    db_session.commit()


class MaxInterventionAttemptsExceededError(Exception):
    pass


class LikelyDataError(Exception):
    pass

class LikelyActionCompletionError(Exception):
    pass

class ImplausibleNoRecentRegistrationsError(Exception):
    pass


def _get_experiment_id(db, experiment_name, return_id=False):
    res = db.query(Experiment.id).filter_by(name=experiment_name).one()
    if return_id:
        res = res.id
    return res
