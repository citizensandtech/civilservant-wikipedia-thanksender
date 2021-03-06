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

pd.set_option('display.max_colwidth', 1000)

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
        self.fname_superthankers = f"superthankers_report_{self.date}.csv"
        self.fname_survey_recips = f"survey_recips_{self.date}.csv"
        self.outfile_yesterday = os.path.join(self.CSVDIR, self.fname_yesterday)
        self.outfile_thankee = os.path.join(self.CSVDIR, self.fname_thankee)
        self.outfile_candidates = os.path.join(self.CSVDIR, self.fname_candidates)
        self.outfile_superthankers = os.path.join(self.CSVDIR, self.fname_superthankers)
        self.outfile_survey_recips = os.path.join(self.CSVDIR, self.fname_survey_recips)
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
        thankee_complete_sql = """with ea as (select json_unquote(metadata_json->'$.lang') as lang, json_unquote(metadata_json->'$.thanks_response.result.recipient') as user_name, if(metadata_json->'$.thanks_sent'=TRUE,1,0) as thanks_sent
                    from core_experiment_actions where action = 'thank' and metadata_json->'$.thanks_sent' = TRUE),
     et as (select json_unquote(metadata_json->'$.sync_object.lang') as lang, json_unquote(metadata_json->'$.sync_object.user_name') as user_name,
              metadata_json->'$.sync_object.user_id' as user_id, metadata_json->'$.sync_object.user_experience_level' as user_experience_level
                    from core_experiment_things where experiment_id=-3 and removed_dt is NULL and randomization_arm=1),
     thanks_sent as (select et.lang, et.user_name, ea.thanks_sent, et.user_experience_level
                    from  et left join ea on et.lang=ea.lang and et.user_name=ea.user_name),
     thanks_complete as (select lang, ifnull(thanks_sent, 0) as thanks_sent, count(*) as num_thanks_sent, user_experience_level
                    from thanks_sent group by lang, thanks_sent, user_experience_level order by lang, thanks_sent),
     cands_et as (select et.lang, cc.user_completed, cc.user_name, et.user_experience_level
                    from et join core_candidates cc on et.lang=cc.lang and et.user_name=cc.user_name),
     cands_complete as (select lang, user_completed, count(*) as thankee_candidates_completed, user_experience_level from cands_et group by lang, user_completed, user_experience_level),
     thanks_cands as (select thanks_complete.lang, cands_complete.user_completed as `completed?`,
        thanks_complete.user_experience_level,
        thankee_candidates_completed as unique_thankees,
        num_thanks_sent as total_thanks_incl_multiples
      from thanks_complete
      join cands_complete
      on thanks_complete.lang = cands_complete.lang
         and thanks_complete.thanks_sent=cands_complete.user_completed
         and thanks_complete.user_experience_level=cands_complete.user_experience_level)
select lang, `completed?`, user_experience_level=0 as `newcomer?`, sum(unique_thankees), sum(total_thanks_incl_multiples)
      from thanks_cands
        where lang!='en'
      group by lang, `completed?`, user_experience_level = 0
      order by lang, `completed?`, `newcomer?`;
"""
        thankee_df = pd.read_sql(thankee_complete_sql, self.db_engine)
        thankee_df.to_csv(self.outfile_thankee, encoding='utf-8')
        self.thankee_html = thankee_df.to_html()


    def thankee_completion_candidates(self):
        thankee_candidates_sql = """select lang, user_completed, count(*) as thankee_candidates from core_candidates group by lang, user_completed;
                                 """
        thankee_df = pd.read_sql(thankee_candidates_sql, self.db_engine)
        logging.info(f"found {thankee_df['thankee_candidates'].sum()} thankee candidates ")
        thankee_df.to_csv(self.outfile_candidates, encoding='utf-8')
        self.thankee_candidates_html = thankee_df.to_html()

    def superthanker_thanks(self):
        superthanker_sql = """with superthanker_thanks as
                                  (select a.action_key_id , o.username, json_unquote(e.metadata_json->'$.sync_object.lang') as lang, json_unquote(e.metadata_json->'$.sync_object.user_name') as user_name, 1 as superthanker
                                    from core_experiment_things e
                                    join core_oauth_users o
                                       on o.username = concat(json_unquote(e.metadata_json->'$.sync_object.lang'), ':' ,json_unquote(e.metadata_json->'$.sync_object.user_name'))
                                    join core_experiment_actions a
                                      on a.action_key_id = o.id
                                  where e.experiment_id=-1 and e.randomization_condition='superthanker' and a.action='thank')
                                
                                select count(*) as num_thanks_sent, lang, user_name
                                  from superthanker_thanks
                                  group by lang, user_name
                                  order by lang, count(*) desc"""
        superthanker_df = pd.read_sql(superthanker_sql, self.db_engine)
        superthanker_df.to_csv(self.outfile_superthankers, encoding='utf-8')
        self.superthanker_thanks_html = superthanker_df.to_html()

    def survey_recipients(self):
        survey_recip_sql = """-- the users that were surveyed recently
select ea.metadata_json->'$.lang' as lang, ea.action_object_id as user_name,
  eab.created_dt as thanked_date,
  concat('https://',json_unquote(ea.metadata_json->'$.lang'),'.wikipedia.org/wiki/', replace(json_unquote(ea.metadata_json->'$.action_response.edit.title'),' ','_')) as contact_page
from core_experiment_actions ea
  join core_experiment_actions eab
     on ea.metadata_json->'$.lang' = eab.metadata_json->'$.lang'
        and ea.action_object_id = eab.metadata_json->'$.thanks_response.result.recipient'
  where ea.action_subject_id='gratitude_thankee_survey'
       and ea.created_dt >= date_sub(curdate(), interval 24 hour)
                                """
        survey_recip_df = pd.read_sql(survey_recip_sql, self.db_engine)
        survey_recip_df.to_csv(self.outfile_survey_recips, encoding='utf-8')
        self.survey_recip_html = survey_recip_df.to_html()

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
        doc_text_2 = f'''<h2>thanker actions status</h2>
<p>This query represents how many thanks have been sent by thankers, and how many users have been marked as completed.
                         </p>'''
        doc_text_4 = f'''<h2>Superthankers thanks given status</h2>
<p>This query represents how many thanks each superthanker has sent.
                         </p>'''
        doc_text_5 = f'''<h2>Yesterday's survey recipients</h2>
<p>This query represents who received surveys yesterday. Users without links represent users inteded to but not surveyed yet.
                         </p>'''
        send_text = doc_text_1 + self.yesterday_html + \
                    doc_text_2 + self.thankee_html + \
                    doc_text_4 + self.superthanker_thanks_html + \
                    doc_text_5 + self.survey_recip_html
        msg.attach(MIMEText(send_text, 'html'))

        for (outfile, fname) in [(self.outfile_yesterday, self.fname_yesterday),
                                 (self.outfile_thankee, self.fname_thankee),
                                 (self.outfile_superthankers, self.fname_superthankers),
                                 (self.outfile_candidates, self.fname_candidates),
                                 (self.outfile_survey_recips, self.fname_survey_recips)]:
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
        self.thankee_completion_candidates()
        self.superthanker_thanks()
        self.survey_recipients()
        self.send_email()
        logging.info("Done running Email report")

if __name__ == "__main__":
    er = EmailReport(lang='en')
    er.run()

