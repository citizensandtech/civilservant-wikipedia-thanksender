import datetime
from civilservant.models.core import ExperimentThing
import civilservant.logs

civilservant.logs.initialize()
import logging


def post_creation_validators(db):
    """
    make sure that the creation stage went as planned.
    :param db:
    :return: has no return value just will raise errors by logging ERROR or CRITICAL
    """
    now = datetime.datetime.utcnow()
    # 0. There was an ET in the last hour.
    hour_ago = now - datetime.timedelta(hours=1)
    last_hour_ets = db.query(ExperimentThing).filter(ExperimentThing.created_dt >= hour_ago).all()
    if len(last_hour_ets)==0:
        logging.info('There were no ETs created in the last hour')
    else:
        logging.info('There were ETs created in the last hour.')

    # 1. Every recent ET has an EA.


def post_execution_validators(db):
    #0. most 10 recent EAs are >50% action completed=TRUE
    #1. no more than 10 action_completed is NULL
    pass
