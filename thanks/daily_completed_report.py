import datetime
import os
import time
import codecs

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
import email.encoders as encoders

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
        self.fname_yesterday = f"{self.subject}.csv"
        self.fname_thankee = f"thankee_completion_report_{self.date}.csv"
        self.fname_candidates = f"thankee_candidates_report_{self.date}.csv"
        self.outfile_yesterday = os.path.join(self.CSVDIR, self.fname_yesterday)
        self.outfile_thankee = os.path.join(self.CSVDIR, self.fname_thankee)
        self.outfile_candidates = os.path.join(self.CSVDIR, self.fname_candidates)
        self.fromaddr = os.getenv("CS_EMAIL_FROMADDR", 'system.operations@civilservant.io')
        self.toaddrs = os.getenv("CS_EMAIL_TOADDRS", ['isalix@gmail.com']).split(',')


    def yesterdays_completers(self):
        yesterday_sql = """select lang, user_name, anonymized_id, condition_,
                          max(action_created_dt) as most_recent_action, count(action) as num_actions
                    
                        from
                          -- get recent experiment actions, decorated
                          ((select json_unquote(ea.metadata_json->'$.lang') as lang, substring(ou.username,4) as user_name, json_unquote(ou.metadata_json->'$.role') as condition_,
                                  ea.action as action, ea.created_dt as action_created_dt, ea.action_object_id thanked_rev, ea.action_key_id as eaaki,
                                  json_unquote(et.metadata_json->"$.sync_object.anonymized_id") as anonymized_id
                                      from core_experiment_actions as ea
                                        join core_oauth_users as ou
                                          on ea.action_key_id=ou.id
                                        join core_experiment_things as et
                                           on  concat("user_name:", ou.username) = et.id
                                       where ea.created_dt >= date_sub(curdate(), interval 24 hour)
                                             and ea.action in ('thank', 'complete_activity') ) recent_thanking
                    
                        join
                          -- get the total number of actions
                            (select action_key_id as eaaki
                                  from core_experiment_actions where action in ('thank', 'complete_activity')
                                  group by action_key_id) num_total_actions
                        on recent_thanking.eaaki = num_total_actions.eaaki)
                    
                    
                    group by lang, user_name, anonymized_id, condition_;

                   """
        yesterday_df = pd.read_sql(yesterday_sql, self.db_engine)
        logging.info(f"found {len(yesterday_df)} completers")
        yesterday_df.to_csv(self.outfile_yesterday, encoding='utf-8')
        self.yesterday_html = yesterday_df.to_html()

    def thankee_completion_status(self):
        thankee_complete_sql = """with  ea as (select json_unquote(metadata_json->"$.lang") as lang, json_unquote(metadata_json->"$.thanks_response.result.recipient") as user_name, metadata_json->"$.thanks_sent" as thanks_sent
                                            from core_experiment_actions where action = 'thank' and metadata_json->"$.thanks_sent" = TRUE),
                                         et as (select json_unquote(metadata_json->"$.sync_object.lang") as lang, json_unquote(metadata_json->"$.sync_object.user_name") as user_name,
                                                  metadata_json->"$.sync_object.user_id" as user_id from core_experiment_things where experiment_id=-3),
                                         ts as (select et.lang, et.user_name, ea.thanks_sent
                                                    from  et left join ea on et.lang=ea.lang and et.user_name=ea.user_name)
                                      select lang, ifnull(thanks_sent, "false") as thanks_sent, count(*) as num_thanks_sent from
                                          ts group by lang, thanks_sent order by lang, thanks_sent
                                """
        thankee_df = pd.read_sql(thankee_complete_sql, self.db_engine)
        logging.info(f"found {thankee_df['num_thanks_sent'].sum()} thankees")
        thankee_df.to_csv(self.outfile_thankee, encoding='utf-8')
        self.thankee_html = thankee_df.to_html()


    def thankee_completion_candidates(self):
        thankee_candidates_sql = """select lang, user_completed, count(*) from core_candidates group by lang, user_completed;
                                 """
        thankee_df = pd.read_sql(thankee_candidates_sql, self.db_engine)
        logging.info(f"found {thankee_df['num_thankees'].sum()} thankees")
        thankee_df.to_csv(self.outfile_thankee, encoding='utf-8')
        self.thankee_candidates_html = thankee_df.to_html()

    def send_email(self):

        COMMASPACE = ', '
        email_subject = f"Daily Gratidude Activity Report for {self.date}"
        msg = MIMEMultipart()
        msg['From'] = self.fromaddr
        msg['To'] = COMMASPACE.join(self.toaddrs)
        msg['Subject'] = email_subject

        doc_text_1 = f'''<h2>{email_subject}</h2>
<p>This query represents all the users who have made Experiment Actions in the previous 24 hours, and their total number of actions ever.
                         </p>'''
        doc_text_2 = f'''<h2>thankee completion status</h2>
<p>This query represents how many thanks have been sent by by thankers (we thought it was the number of thankees, but a bug meant that until 2019.8.8 a thankee was being thanked multiple times).
                         </p>'''
        doc_text_3 = f'''<h2>thankee candidates status</h2>
<p>This query represents how many thankees "candidates" have been marked as completed.
                         </p>'''
        send_text = doc_text_1 + self.yesterday_html + doc_text_2 + self.thankee_html + doc_text_3 + self.thankee_candidates_html
        msg.attach(MIMEText(send_text, 'html'))
        for (outfile, fname) in [(self.outfile_yesterday, self.fname_yesterday),
                                 (self.outfile_thankee, self.fname_thankee),
                                 (self.outfile_candidates, self.fname_candidates)]:
            with codecs.open(outfile, 'r', encoding='utf8') as f:
                text = f.read()
                part = MIMEText(text, 'csv', 'utf-8')
                part['Content-Disposition'] = f'attachment; filename="{fname}"'
                msg.attach(part)

        server = smtplib.SMTP('localhost', 25)
        text = msg.as_string()
        server.sendmail(self.fromaddr, self.toaddrs, text)
        server.quit()
        logging.info("Sent email from {0} to {1} recipients".format(self.fromaddr, self.toaddrs))

    def run(self):
        self.yesterdays_completers()
        self.thankee_completion_status()
        self.thankee_candidates_html()
        self.send_email()
        logging.info("Done running Email report")

if __name__ == "__main__":
    er = EmailReport(lang='en')
    er.run()

