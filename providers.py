import random
from datetime import timedelta

from indicate_data_exchange_api_client import AggregationPeriodKind, \
    AggregatedQualityIndicatorResult


class DataProviderBase:
    def get_overview(self, period: AggregationPeriodKind, start_date, end_date):
        raise NotImplementedError()

    def get_indicator_detail(self, indicator_id, period: AggregationPeriodKind, start_date, end_date):
        raise NotImplementedError()


class RandomDataProvider(DataProviderBase):
    def __init__(self, num_hospitals=8, num_indicators=8, seed=42):
        self.num_hospitals = num_hospitals
        self.num_indicators = num_indicators
        self.seed = seed

    def _date_range(self, period, start, end):
        days = (end - start).days
        if period == 'weekly':
            period_days = 7
        elif period == 'monthly':
            period_days = 30
        elif period == 'yearly':
            period_days = 365
        for i in range(0, days, period_days):
            yield start + timedelta(days=i)

    def _rand_series(self, seed_base, period, start, end):
        r = random.Random(seed_base)
        series = []
        for d in self._date_range(period, start, end):
            # base value between 50 and 95
            base = r.uniform(0.50, 0.95)
            # add small day-to-day noise
            noise = r.uniform(-0.08, 0.08)
            val = max(0.0, min(1.0, base + noise))
            series.append((d, val))
        return series

    def get_overview(self, period: AggregationPeriodKind, start_date, end_date):
        indicators = []
        for iid in range(1, self.num_indicators + 1):
            name = f"Indicator {iid}"
            num_patients = random.Random(self.seed + iid).randint(50, 1200)
            # each indicator has an 'all hospitals' average and 'own' hospital
            all_series = self._rand_series(seed_base=(self.seed + iid * 100),
                                           period=period,
                                           start=start_date,
                                           end=end_date)
            own_series = self._rand_series(seed_base=(self.seed + iid * 1000),
                                           period=period,
                                           start=start_date,
                                           end=end_date)
            avg_all = sum(v for _, v in all_series) / len(all_series) if all_series else 0
            avg_own = sum(v for _, v in own_series) / len(own_series) if own_series else 0
            if avg_own < avg_all:
                rank = random.randint(1, self.num_hospitals // 2)
            else:
                rank = random.randint(max(1, self.num_hospitals // 2), self.num_hospitals)
            history = [{'date': d, 'value': v, 'observation_count': 100} for d, v in own_series]
            indicators.append({
                'id':            iid,
                'name':          name,
                'num_hospitals': self.num_hospitals,
                'num_patients':  num_patients,
                'avg_own':       avg_own,
                'avg_all':       avg_all,
                'rank':          rank,
                'history':       history,
            })

        return { 'with_provider_id': True, 'indicators': indicators }

    def get_indicator_detail(self, indicator_id, period: AggregationPeriodKind, start_date, end_date):
        if indicator_id < 1 or indicator_id > self.num_indicators:
            return None

        name = f"Indicator {indicator_id}"
        description = f"Detailed description for {name}. This explains how adherence is computed and what it means."

        # For each hospital produce a row
        providers_temp = []
        seeds = [self.seed + indicator_id * 100 + i for i in range(self.num_hospitals)]
        for i, s in enumerate(seeds):
            ser = self._rand_series(seed_base=s, period=period, start=start_date, end=end_date)
            avg = sum(v for _, v in ser) / len(ser) if ser else 0
            providers_temp.append({'avg': avg, 'series': ser})
        providers_temp.sort(key=lambda x: x['avg'], reverse=True)

        # pick one index as 'own' hospital; let's choose the middle index
        own_index = len(providers_temp) // 2
        providers = []
        for rank, info in enumerate(providers_temp, start=1):
            avg, ser = info['avg'], info['series']
            label = "My Location" if rank == own_index else "********"
            providers.append({
                'rank':         rank,
                'label':        label,
                'num_patients': random.Random(self.seed + indicator_id * 13 + rank).randint(10, 800),
                'avg':          avg,
                'history':      [{'date': d, 'value': v, 'observation_count': 100} for d, v in ser],
            })
        return {'id': indicator_id,
                'name': name,
                'description': description,
                'providers': providers}


class OpenAPIDataProvider(DataProviderBase):
    def __init__(self, hub, provider_id, provider_name):
        self.hub = hub
        self.provider_id = provider_id
        self.provider_name = provider_name

    def _get_indicators_info(self):
        return self.hub.indicator_info()


    def get_overview(self, period: AggregationPeriodKind, start_date, end_date):
        # Get meta-data (title, description, etc.) for all indicators.
        # TODO: could cache this
        indicators_info = self._get_indicators_info()
        def find_indicator_info(indicator_id):
            return next((indicator_info for indicator_info in indicators_info
                         if indicator_info.concept_id == indicator_id),
                        None)

        # Get
        response = self.hub.results(period, period_start=start_date, period_end=end_date)
        #
        indicator_results = {}
        def ensure_indicator(indicator_id):
            if indicator_id not in indicator_results:
                indicator_info = find_indicator_info(indicator_id)
                indicator_results[indicator_id] = {
                    'id':                 indicator_id,
                    'title':              indicator_info.title,
                    'providers':          {},
                    'values':             [],
                    'observation_counts': [],
                    'history':            {},
                }
            return indicator_results[indicator_id]
        def add_to_provider(indicator_result, provider, observation):
            providers = indicator_result['providers']
            if provider not in providers:
                providers[provider] = []
            providers[provider].append(observation)
        def add_to_history(history, observation: AggregatedQualityIndicatorResult):
            cell = history.get(observation.aggregation_period_start, None)
            if cell is None:
                cell = {
                    'date':               observation.aggregation_period_start.date(),
                    'values':             [],
                    'observation_counts': [],
                }
                history[observation.aggregation_period_start.date()] = cell
            cell['values'].append(observation.average_value)
            cell['observation_counts'].append(observation.observation_count)

        for quality_indicator_data in response:
            indicator_result = ensure_indicator(quality_indicator_data.indicator_id)
            add_to_provider(indicator_result, quality_indicator_data.provider_id, quality_indicator_data)
            indicator_result['values'].append(quality_indicator_data.average_value)
            indicator_result['observation_counts'].append(quality_indicator_data.observation_count)
            add_to_history(indicator_result['history'], quality_indicator_data)

        #
        def safe_average(sequence, length=None):
            if length is None:
                length = len(sequence)
            return sum(sequence) / length if length > 0 else 0

        # Replace the "values" property of each history cell with a
        # "value" property that is the average of the
        # values. Similarly, replace the "observation_counts" cell
        # with an "observation_count" that is the sum of the
        # observation counts.
        def aggregate_history(history):
            return [
                {
                    "date":              cell["date"],
                    "value":             safe_average(cell["values"]),
                    "observation_count": sum(cell["observation_counts"])
                }
                for cell in sorted(history.values(), key=lambda cell: cell["date"])
            ]
        def format_indicator_result(indicator_result):
            history = aggregate_history(indicator_result['history'])
            result = {
                'id':            indicator_result['id'],
                'name':          indicator_result['title'],
                'num_hospitals': len(indicator_result['providers']),
                'num_patients':  safe_average([ cell["observation_count"] for cell in history ]),
                'avg_all':       safe_average([ cell['value'] for cell in history]),
                'history':       history,
                'avg_own':       0,
                'rank':          0,
            }
            if self.provider_id is not None:
                provider_averages = sorted([ (provider_id, safe_average([ result.average_value for result in provider_results ]))
                                             for provider_id, provider_results in indicator_result['providers'].items() ],
                                           key=lambda cell: cell[1], reverse=True)
                for i, (provider_id, average_value) in enumerate(provider_averages):
                    if provider_id == self.provider_id:
                        result['avg_own'] = average_value
                        result['rank']    = i + 1
                        break
            return result
        return {
            'with_provider_id': self.provider_id is not None,
            'indicators':       [ format_indicator_result(indicator_result)
                                  for indicator_result in indicator_results.values() ]
        }

    def get_indicator_detail(self, indicator_id, period: AggregationPeriodKind, start_date, end_date):
        indicators_info = self._get_indicators_info()
        # TODO: handle error
        indicator_info = next((info for info in indicators_info if info.concept_id == indicator_id), None)
        response = self.hub.results(period, period_start=start_date, period_end=end_date)
        provider_results = {}

        def ensure_provider(provider_id):
            if provider_id not in provider_results:
                provider_results[provider_id] = {
                    'provider_id':        provider_id,
                    'history':            [],
                    'values':             [],
                    'observation_counts': [],
                }
            return provider_results[provider_id]

        for quality_indicator_data in response:
            if quality_indicator_data.indicator_id == indicator_id:
                provider_result = ensure_provider(quality_indicator_data.provider_id)
                provider_result['history'].append({
                    'date':              quality_indicator_data.aggregation_period_start.date(),
                    'value':             quality_indicator_data.average_value,
                    'observation_count': quality_indicator_data.observation_count
                })
                provider_result['values'].append(quality_indicator_data.average_value)
                provider_result['observation_counts'].append(quality_indicator_data.observation_count)
        #
        def format_provider_data(provider_result):
            is_self = (provider_result['provider_id'] == self.provider_id)
            return {
                'is_self':      is_self,
                'label':        self.provider_name if is_self else '*' * 6,
                'num_patients': sum(provider_result['observation_counts']) / len(provider_result['observation_counts']),
                'avg':          sum(provider_result['values']) / len(provider_result['values']),
                'history':      provider_result['history'],
            }
        # Sort data provider-specific results by average adherence value, highest adherence first.
        sorted_providers = sorted([ format_provider_data(provider_result)
                                    for provider_result in provider_results.values() ],
                                  key=lambda cell: cell['avg'], reverse=True)
        # Assign ranks from 1 to N to the sorted items.
        ranked_providers = [ { 'rank': i + 1, **cell} for i, cell in enumerate(sorted_providers) ]
        return {
            'with_provider_id': self.provider_id is not None,
            'id':               indicator_id,
            'name':             indicator_info.title,
            'description':      indicator_info.description,
            'providers':        ranked_providers,
        }
