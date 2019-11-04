from thanks.periodic_report import EmailReport
from thanks.utils import _get_experiment_id
import datetime

class WelcomeReport(EmailReport):
    def __init__(self):
        super().__init__()

        self.now = datetime.datetime.utcnow()
        self.add_12_hourly()
        self.add_deliverability()

    def add_12_hourly(self):
        query_name = '12 hourly report'
        query_sql = '''select * from core_experiment_actions 
                            where experiment_id=%(experiment_id)s
                            and created_dt <= %(end_date)s
                            and created_dt >= %(start_date)s
                            '''
        query_params = {'experiment_id': self.experiment_id,
                        'start_date': self.now - datetime.timedelta(hours=12),
                        'end_date': self.now
                        }
        query_description = f'''Experiment Actions created in the last 12 hours.'''
        self.add_query(query_name=query_name,
                          query_sql=query_sql,
                          query_params=query_params,
                          query_description=query_description)

    def add_deliverability(self):
        query_name = 'deliverability report'
        query_sql = '''select * from core_experiment_actions 
                            where experiment_id=%(experiment_id)s
                            and created_dt <= %(end_date)s
                            and created_dt >= %(start_date)s
                            '''
        query_params = {'experiment_id': self.experiment_id,
                        'start_date': self.now - datetime.timedelta(hours=12),
                        'end_date': self.now
                        }
        query_description = f'''Experiment Actions created in the last 12 hours.'''
        self.add_query(query_name=query_name,
                          query_sql=query_sql,
                          query_params=query_params,
                          query_description=query_description)

if __name__ == '__main__':
    wr = WelcomeReport()
    wr.run()
