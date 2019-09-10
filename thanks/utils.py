from sqlalchemy.orm.attributes import flag_modified

def update_action_status(db_session, logging, experiment_action):
    logging.debug(f"In update status with metadata {experiment_action.metadata_json}")
    flag_modified(experiment_action, "metadata_json")
    db_session.add(experiment_action)
    db_session.commit()


class MaxInterventionAttemptsExceededError(Exception):
    pass


