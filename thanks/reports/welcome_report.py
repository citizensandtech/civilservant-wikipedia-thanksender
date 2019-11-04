from thanks.periodic_report import EmailReport
from thanks.utils import _get_experiment_id
import datetime

class WelcomeReport(EmailReport):
    def __init__(self):
        super().__init__()

        now =  datetime.datetime.utcnow()
        query_name = '12 hourly report'
        query_sql = '''select * from core_experiment_actions 
                            where experiment_id=%(experiment_id)s
                            and created_dt <= %(end_date)s
                            and created_dt >= %(start_date)s
                            '''
        query_params = {'experiment_id': self.experiment_id,
                        'start_date': now-datetime.timedelta(hours=12),
                        'end_date': now
                        }
        query_description = f'''Experiment Actions created in the last 12 hours.'''
        super().add_query(query_name=query_name,
                          query_sql=query_sql,
                          query_params=query_params,
                          query_description=query_description)


if __name__ == '__main__':
    wr = WelcomeReport()
    wr.run()
