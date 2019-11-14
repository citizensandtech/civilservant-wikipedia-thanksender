import datetime
import os
import time
import codecs

from sqlalchemy import and_, or_, func, desc
import sqlalchemy
import civilservant.logs
from civilservant.util import PlatformType, ThingType, read_config_file

from thanks.utils import _get_experiment_id

civilservant.logs.initialize()
import logging
from civilservant.db import init_engine, init_session
import pandas as pd

pd.set_option('display.max_colwidth', 1000)

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import email.encoders as encoders


class EmailReport:
    """
    CivilServant Email Report
    """

    def __init__(self, config=None):
        self.config = read_config_file(os.environ['CS_EXTRA_CONFIG_FILE'], __file__)
        self.db_engine = init_engine()
        self.db_session = init_session()
        if 'name' in self.config.keys():
            self.experiment_id = _get_experiment_id(self.db_session, self.config['name'], return_id=True)
        self.csv_dir = os.path.join(self.config["dirs"]['project'], self.config["dirs"]['reports'])
        self.date = datetime.datetime.today().strftime('%Y%m%d')
        self.queries = {}
        self.to_addrs = self.config['reports']['to_addrs']
        self.from_addr = self.config['reports']['from_addr']
        self.subject_stat = None

    def add_query(self, query_name, query_sql, query_params, query_description, subject_stat_fn=None,
                  post_exec_fn=None):
        """
        add a query to be process
        :param query_name: a unique name for this query
        :param query_sql: the sql to execute with %()s param placeholders
        :param query_params: dict of params to put in the placeholdesr
        :param query_description: natural language explanation of query to put in email
        :param subject_stat_fn: a fn of the result df to prepend to email title (one per report)
        :param post_exec_fn: a df-->df fn to execute after the sql executes
        :return:
        """
        self.queries[query_name] = {}
        self.queries[query_name]['sql_f'] = query_sql
        self.queries[query_name]['sql_params'] = query_params
        self.queries[query_name]['description'] = query_description
        self.queries[query_name]['stat_fn'] = subject_stat_fn
        self.queries[query_name]['post_exec_fn'] = post_exec_fn

    def run_queries(self):
        """
        runs all the queries and put their results back in to self.queries dict with 'outfile' and 'html' keys
        :return:
        """
        for query_name, query_parts in self.queries.items():
            query_sql_params = query_parts['sql_params']
            query_sql = query_parts['sql_f']
            df = pd.read_sql(sql=query_sql, con=self.db_engine, params=query_sql_params)
            logging.info(f"completed {query_name} query")

            # run a python post processor if specified
            post_exec_fn = query_parts['post_exec_fn'] if 'post_exec_fn' in query_parts else None
            if post_exec_fn:
                df = post_exec_fn(df)

            # make a summary stat if specified
            query_subject_stat_fn = query_parts['stat_fn'] if 'stat_fn' in query_parts else None
            if query_subject_stat_fn:
                self.subject_stat = query_subject_stat_fn(df)

            # output a CSV version of the result
            f_name = f'{query_name}_{self.date}.csv'
            outfile = os.path.join(self.csv_dir, f_name)
            self.queries[query_name]['fname'] = f_name
            self.queries[query_name]['outfile'] = outfile
            df.to_csv(outfile, encoding='utf-8')
            self.queries[query_name]['html'] = df.to_html()

    def send_email(self):
        COMMASPACE = ', '
        email_subject_title = self.config['reports']['email_subject']
        subject_prefix = ''
        if self.subject_stat:
            subject_prefix = f'{self.subject_stat} | '
        email_subject = f"{subject_prefix}{email_subject_title} for {self.date}"
        msg = MIMEMultipart()
        msg['From'] = self.from_addr
        msg['To'] = COMMASPACE.join(self.to_addrs)
        msg['Subject'] = email_subject

        send_text = ""

        for query_name, query_parts in self.queries.items():
            heading = f'<h2>{query_name}</h2>'
            description = f'<p>{query_parts["description"]}</p>'
            table = query_parts['html']

            send_text += heading
            send_text += description
            send_text += table
            send_text += '<br/><hr/><br/>'

        msg.attach(MIMEText(send_text, 'html'))

        for query_name, query_parts in self.queries.items():
            outfile = self.queries[query_name]['outfile']
            fname = self.queries[query_name]['fname']
            with codecs.open(outfile, 'r', encoding='utf8') as f:
                text = f.read()
                part = MIMEText(text, 'csv', 'utf-8')
                part['Content-Disposition'] = f'attachment; filename="{fname}"'
                msg.attach(part)

        server = smtplib.SMTP('localhost', 25)
        text = msg.as_string()
        server.sendmail(self.from_addr, self.to_addrs, text)
        server.quit()
        logging.info("Sent email from {0} to {1} recipients".format(self.from_addr, self.to_addrs))

    def run(self):
        logging.info("Starting to run Email report")
        self.run_queries()
        self.send_email()
        logging.info("Done running Email report")


if __name__ == "__main__":
    er = EmailReport(lang='en')
    er.run()
