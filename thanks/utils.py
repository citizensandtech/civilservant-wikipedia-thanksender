from civilservant.models.core import Experiment, ExperimentAction
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


def _get_num_experiment_actions(db, experiment_id=None, action=None):
    EAs_q = db.query(ExperimentAction)
    if experiment_id:
        EAs_q = EAs_q.filter(ExperimentAction.experiment_id == experiment_id)
    if action:
        EAs_q = EAs_q.filter(ExperimentAction.action == action)
    return EAs_q.count()
