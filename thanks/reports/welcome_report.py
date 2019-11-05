from thanks.periodic_report import EmailReport
from thanks.utils import _get_experiment_id
import datetime


class WelcomeReport(EmailReport):
    def __init__(self):
        super().__init__()

        self.now = datetime.datetime.utcnow()
        self.add_12_hourly()
        self.add_total_activity()

    def add_12_hourly(self):
        query_name = '12 hourly report'
        query_sql = '''select created_dt,
                              json_unquote(metadata_json->'$.lang') as lang, 
                              json_unquote(metadata_json->'$.user_name') as user_name,
                              concat('https://fr.wikipedia.org/wiki/',
                                  json_unquote(metadata_json->'$.action_response.edit.title')) as invite_link
                            from core_experiment_actions 
                            where experiment_id=%(experiment_id)s
                            and created_dt <= %(end_date)s
                            and created_dt >= %(start_date)s
                            '''
        query_params = {'experiment_id': self.experiment_id,
                        'start_date': self.now - datetime.timedelta(hours=12),
                        'end_date': self.now
                        }
        query_description = f'''Experiment actions created in the last 12 hours.'''
        subject_stat_fn = lambda df: f'{len(df)} new users welcomed in last 12 hours'
        self.add_query(query_name=query_name,
                       query_sql=query_sql,
                       query_params=query_params,
                       query_description=query_description,
                       subject_stat_fn=subject_stat_fn)

    def add_total_activity(self):
        query_name = 'total_activity'
        query_sql = '''select 
                        metadata_json->'$.action_complete' as 'completed?', 
                        count(*)
                        from core_experiment_actions where experiment_id=%(experiment_id)s
                        group by metadata_json->'$.action_complete';'''
        query_params = {'experiment_id': self.experiment_id}
        query_description = f'''Total activity ever in the welcome experiment.'''
        self.add_query(query_name=query_name,
                       query_sql=query_sql,
                       query_params=query_params,
                       query_description=query_description)


if __name__ == '__main__':
    wr = WelcomeReport()
    wr.run()
