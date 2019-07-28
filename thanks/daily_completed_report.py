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


class EmailReport:
    """
    mostly acts on the metadata_json field. Field data codes
    - thanks_sent:
       - key doesnt exist --> not yet tried or  have only been errors sending
       - True --> successfully sent
       - False --> cannot be sent for some reason
    - errors:
       - key doesn't exist --> not yet tried or success on first time
       - list of dicts --> {dt: errorstr} #TODO if uncaught error have a dict that contains the stracktrace etc.
    """

    def __init__(self, lang=None):
        logging.info(f"Thanking batch size set to : {self.thank_batch_size}")
        self.db_engine = init_engine()
        self.lang = lang
        self.CSVDIR = os.getenv('CS_CSV_REPORT_DIR', "reports")
        self.fname = f"gratitude_complet_report_{datetime.datetime.today().strftime('%Y%m%d')}"
        self.outfile = os.path.join(self.CSVDIR, self.fname)


    def yesterdays_completers(self):
        # now = datetime.datetime.utcnow()
        # time_epsilon = datetime.timedelta(hours=1)
        # yesterday = now - (datetime.timedelta(days=1) + time_epsilon)
        # logging.info(f"Now is {now} . Yesterday with epsilon was {yesterday} .")
        # date_cond = OAuthUser.modified_dt >= yesterday
        # activity_completed = OAuthUser.metadata_json['role'] == 'activity'
        # thank_completed = and_(OAuthUser.metadata_json['role'] == 'thank', OAuthUser.metadata_json['thanks_count'] >=4)
        #
        # yesterday_query = self.db_session.query(OAuthUser).filter(date_cond) \
        #                       .filter(or_(activity_completed, thank_completed))
        # return yesterday_query.all()
        yesterday_sql = """select * from core_oauth_users
                            where modified_dt > date_sub(curdate(), interval 25 hour)
                              and (metadata_json->"$.role"='activity' or
                                   metadata_json->"$.role"='thank' and metadata_json->"$.thanks_count" >= 4);
                        """
        yesterday_df = pd.read_sql(yesterday_sql, self.db_engine)
        yesterday_df.to_csv(self.outfile, index=False)



    def send_email(fromaddr, toaddrs, subject, html):

        COMMASPACE = ', '

        msg = MIMEMultipart()
        msg['From'] = fromaddr
        msg['To'] = COMMASPACE.join(toaddrs)
        msg['Subject'] = subject

        body = html
        msg.attach(MIMEText(body, 'html'))

        server = smtplib.SMTP('localhost', 25)
        text = msg.as_string()
        server.sendmail(fromaddr, toaddrs, text)
        server.quit()
        print("Sent email from {0} to {1} recipients".format(fromaddr, len(toaddrs)))

    def run(self):
        completers = self.yesterdays_completers()
        logging.info(f"found {len(completers) completers}")

if __name__ == "__main__":
    er = EmailReport(lang='en')
    er.run()

