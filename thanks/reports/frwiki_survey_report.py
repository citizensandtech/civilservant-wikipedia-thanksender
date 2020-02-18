from thanks.periodic_report import EmailReport
import datetime


class WelcomeReport(EmailReport):
    def __init__(self):
        super().__init__()

        self.now = datetime.datetime.utcnow()
        self.add_total_activity()
        self.add_24_hourly()

    def add_24_hourly(self):
        query_name = '24 hourly report'
        query_sql = '''select created_dt,
                              json_unquote(metadata_json->'$.lang') as lang,
                              json_unquote(metadata_json->'$.user_name') as user_name,
                              replace(concat('https://fr.wikipedia.org/wiki/User_talk:',
                                  json_unquote(metadata_json->'$.user_name')), ' ', '_') as user_talk_page,
                              metadata_json->'$.action_complete' as survey_sent
                            from core_experiment_actions
                            where experiment_id=%(experiment_id)s
                            and created_dt <= %(end_date)s
                            and created_dt >= %(start_date)s
                            order by survey_sent desc;
                            '''
        n_hours_ago = self.now - datetime.timedelta(hours=24)
        query_params = {'experiment_id': self.experiment_id,
                        'start_date': n_hours_ago,
                        'end_date': self.now
                        }
        query_description = f'''Survey experiment actions created in the last between {n_hours_ago} and {self.now}.'''
        subject_stat_fn = lambda df: f'{len(df)} new users surveyed in last 24 hours'
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
        query_description = f'''How many users have been surveyed in the fr wiki experiment.'''
        self.add_query(query_name=query_name,
                       query_sql=query_sql,
                       query_params=query_params,
                       query_description=query_description)


if __name__ == '__main__':
    wr = WelcomeReport()
    wr.run()
