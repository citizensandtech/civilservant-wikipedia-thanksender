import datetime
import os
import time

from sqlalchemy import and_, or_, func, desc
import sqlalchemy
import civilservant.logs
from civilservant.util import PlatformType, ThingType

civilservant.logs.initialize()
import logging
from civilservant.db import init_engine
from civilservant.models.core import OAuthUser
import pandas as pd

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication


class EmailReport:
    """
    Note for usage on studies.civilservant.io. Use editsync's virtualenv
    """

    def __init__(self, lang=None):
        self.db_engine = init_engine()
        self.lang = lang
        self.CSVDIR = os.getenv('CS_EMAIL_CSV_REPORT_DIR', "reports")
        self.date = datetime.datetime.today().strftime('%Y%m%d')
        self.subject = f"gratitude_completed_report_{self.date}"
        self.fname = f"{self.subject}.csv"
        self.outfile = os.path.join(self.CSVDIR, self.fname)
        self.fromaddr = os.getenv("CS_EMAIL_FROMADDR", 'system.operations@civilservant.io')
        self.toaddrs = os.getenv("CS_EMAIL_TOADDRS", ['isalix@gmail.com']).split(',')

        
    def yesterdays_completers(self):
        yesterday_sql = """select lang_user_name, max(condition_) as condition_, max(action_created_dt) as most_recent_action_dt, count(action) as num_actions_ever from
                                ((select ou.username as lang_user_name, ou.metadata_json->'$.role' as condition_,
                                                    ea.action as action, ea.created_dt as action_created_dt, ea.action_object_id thanked_rev, ea.action_key_id as eaaki
                                                        from core_experiment_actions as ea join core_oauth_users ou
                                                        on ea.action_key_id=ou.id
                                                           where ea.created_dt >= date_sub(curdate(), interval 24 hour)
                                                                 and ea.action in ('thank', 'complete_activity') ) recent_thanking
                                            join
                                              (select action_key_id as eaaki
                                                    from core_experiment_actions where action in ('thank', 'complete_activity')
                                                    group by action_key_id) num_total_actions
                                            on recent_thanking.eaaki = num_total_actions.eaaki)
                                        group by lang_user_name;
                                                """
        yesterday_df = pd.read_sql(yesterday_sql, self.db_engine)
        logging.info(f"found {len(yesterday_df)} completers")
        yesterday_df.to_csv(self.outfile)
        self.yesterday_html = yesterday_df.to_html()


    def send_email(self):

        COMMASPACE = ', '
        email_subject = f"Daily Gratidude Activity Report for {self.date}"
        
        msg = MIMEMultipart()
        msg['From'] = self.fromaddr
        msg['To'] = COMMASPACE.join(self.toaddrs)
        msg['Subject'] = email_subject

        doc_text = f'''<h1>{email_subject}</h1>
<p>This query represents all the users who have made Experiment Actions in the previous 24 hours, and their total number of actions ever.
                         </p>'''
        send_text = doc_text + self.yesterday_html
        msg.attach(MIMEText(send_text, 'html'))
        with open(self.outfile, 'r') as f:
            part = MIMEApplication(f.read(), Name=self.fname)
        part['Content-Disposition'] = f'attachment; filename="{self.fname}"'
        msg.attach(part)
        
        server = smtplib.SMTP('localhost', 25)
        text = msg.as_string()
        server.sendmail(self.fromaddr, self.toaddrs, text)
        server.quit()
        logging.info("Sent email from {0} to {1} recipients".format(self.fromaddr, self.toaddrs))

    def run(self):
        self.yesterdays_completers()
        self.send_email()
        logging.info("Done running Email report")

if __name__ == "__main__":
    er = EmailReport(lang='en')
    er.run()

