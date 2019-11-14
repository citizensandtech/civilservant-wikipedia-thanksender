from thanks.periodic_report import EmailReport
import datetime


class SkipReport(EmailReport):
    def __init__(self):
        super().__init__()

        self.now = datetime.datetime.utcnow()
        self.today = datetime.date.today()
        self.add_skip_stats()

    def add_skip_stats(self):
        query_name = 'Skip stats'
        query_sql = '''with thankees as (select cet.metadata_json->'$.sync_object.lang' as lang,
                        cet.metadata_json->'$.sync_object.user_name' as user_name,
                        date(cet.created_dt) as onboard_date,
                        cc.user_completed as user_completed,
                        cc.user_experience_level as user_experience_level
                      from core_experiment_things cet
                        join core_candidates cc
                          on cet.metadata_json->'$.sync_object.lang'=cc.lang
                            and cet.metadata_json->'$.sync_object.user_name'=cc.user_name
                      where experiment_id=-3
                            and randomization_arm=1
                            and removed_dt is NULL),
                        skip_counts as (select metadata_json->'$.lang' as lang,
                                          action_object_id as user_name,
                                          count(*)         as num_skips
                                        from core_experiment_actions
                                        where action='skip' group by action_object_id, metadata_json->'$.lang')
                    select thankees.lang,
                      thankees.user_name,
                      thankees.user_completed,
                      thankees.user_experience_level,
                      thankees.onboard_date,
                      skip_counts.num_skips
                    from thankees
                    left join skip_counts
                    on thankees.lang = skip_counts.lang and thankees.user_name=skip_counts.user_name;
                '''
        query_params = {}
        query_description = f'''Skipping statistics for thankees onboarded in the last 90 days. How often they were skipped.'''

        def skip_post_exec_fn(df):
            df['newcomer'] = df['user_experience_level'].apply(lambda uel: uel == '0')
            df = df[df['lang'] != 'en']
            ninety_days_ago = self.today - datetime.timedelta(days=90)
            recent_df = df[df['onboard_date'] >= ninety_days_ago]
            groups = recent_df.groupby(['lang', 'user_completed', 'newcomer'])

            def num_in_group(series):
                return sum(1 for skip_count in series)

            def num_skipped_zero(series):
                return sum(1 for skip_count in series if skip_count == 0)

            def num_skipped_at_least_once(series):
                return sum(1 for skip_count in series if skip_count >= 1)

            def num_skipped_at_least_twice(series):
                return sum(1 for skip_count in series if skip_count >= 2)

            skip_stats = groups.agg({'num_skips': [num_in_group,
                                                   num_skipped_zero,
                                                   num_skipped_at_least_once,
                                                   num_skipped_at_least_twice]})

            skip_stats.columns = skip_stats.columns.get_level_values(1)

            skip_stats['%skipped zero'] = skip_stats['num_skipped_zero'] / skip_stats['num_in_group']
            skip_stats['%skipped once'] = skip_stats['num_skipped_at_least_once'] / skip_stats['num_in_group']
            skip_stats['%skipped twice'] = skip_stats['num_skipped_at_least_twice'] / skip_stats['num_in_group']

            return skip_stats

        self.add_query(query_name=query_name,
                       query_sql=query_sql,
                       query_params=query_params,
                       query_description=query_description,
                       post_exec_fn=skip_post_exec_fn)


if __name__ == '__main__':
    wr = SkipReport()
    wr.run()
