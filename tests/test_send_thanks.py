import json
import os
from unittest.mock import patch

import logging

import mwapi
from civilservant.db import init_session
from civilservant.models.core import ExperimentAction

import pytest

from thanks.send_thanks import thanksSender


def load_path_files_to_dict(sub_dirname, filetype):
    sub_dir = os.path.join('test_data', sub_dirname)
    fname_file = {f: json.load(open(os.path.join(sub_dir, f), 'r')) for f in os.listdir(sub_dir) if f.endswith(filetype)}
    return fname_file


@pytest.fixture
def mwapi_responses():
    return load_path_files_to_dict('mwapi_responses','.json')


@pytest.fixture(scope="module")
def db_session():
    session = init_session()
    yield session
    session.close()

def setup_data(db_session):
    db_session.query(ExperimentAction).delete()
    db_session.commit()
    db_session.execute("""INSERT INTO civilservant_test.core_experiment_actions (id, created_dt, experiment_id, action_key_id, action, action_subject_type, action_subject_id, action_object_type, action_object_id, metadata_json, action_platform, removed_dt) VALUES (1, '2019-07-20 07:07:02', -1, '2', 'thank', 'ThingType.WIKIPEDIA_USER', null, 'ThingType.WIKIPEDIA_EDIT', '899651833', '{"lang":"en"}', null, null);""")
    db_session.execute("""INSERT INTO civilservant_test.core_experiment_actions (id, created_dt, experiment_id, action_key_id, action, action_subject_type, action_subject_id, action_object_type, action_object_id, metadata_json, action_platform, removed_dt) VALUES (2, '2019-07-20 07:07:02', -1, '1', 'thank', 'ThingType.WIKIPEDIA_USER', null, 'ThingType.WIKIPEDIA_EDIT', '906577052', '{"lang":"en"}', null, null);""")
    db_session.execute("""INSERT INTO civilservant_test.core_experiment_actions (id, created_dt, experiment_id, action_key_id, action, action_subject_type, action_subject_id, action_object_type, action_object_id, metadata_json, action_platform, removed_dt) VALUES (3, '2019-07-20 23:44:38', -1, '5', 'thank', 'ThingType.WIKIPEDIA_USER', null, 'ThingType.WIKIPEDIA_EDIT', '56662991', '{"lang":"en"}', null, null);""")
    db_session.commit()

@patch('mwapi.Session.get')
@patch('mwapi.Session.post')
def test_successful_send(mock_mwapi_session_post, mock_mwapi_session_get, mwapi_responses, db_session):
    n_items = 3
    mock_mwapi_session_get.side_effect = [mwapi_responses['csrf.json']] * n_items
    mock_mwapi_session_post.side_effect = [mwapi_responses['success.json']] * n_items
    setup_data(db_session)
    ts = thanksSender(thank_batch_size=n_items)
    ts.run()
    assert len(db_session.query(ExperimentAction).filter(ExperimentAction.metadata_json['thanks_sent']==True).all()) == n_items

@patch('mwapi.Session.get')
@patch('mwapi.Session.post')
def test_network_down(mock_mwapi_session_post, mock_mwapi_session_get, mwapi_responses, db_session):
    n_items = 3
    mock_mwapi_session_get.side_effect = [mwapi_responses['csrf.json']] * n_items
    mock_mwapi_session_post.side_effect = []
    setup_data(db_session)
    ts = thanksSender(thank_batch_size=n_items)
    ts.run()
    assert len(db_session.query(ExperimentAction).filter(ExperimentAction.metadata_json['thanks_sent']==None).all()) == n_items
    error_items = db_session.query(ExperimentAction).filter(ExperimentAction.metadata_json['thanks_sent']==None).all()
    for ei in error_items:
        assert isinstance(ei.metadata_json['errors'], list)
