import urllib2
import requests
import time
import datetime
import dateutil.parser
from requests import Request

class PyBingException(Exception):
    pass


class PyBingSearch(object):

    QUERY_URL = 'https://api.datamarket.azure.com/Bing/SearchWeb/Web' \
                 + '?Query={}&$top={}&$skip={}&$format={}'

    def __init__(self, api_key, safe=False):
        self.api_key = api_key
        self.safe = safe

    def search(self, query, limit=50, offset=0, format='json'):
        ''' Returns the result list, and also the uri for next page (returned_list, next_uri) '''
        return self._search(query, limit, offset, format)

    def search_all(self, query, limit=50, format='json'):
        ''' Returns a single list containing up to 'limit' Result objects'''
        results, next_link = self._search(query, limit, 0, format)
        while next_link and len(results) < limit:
            max = limit - len(results)
            more_results, next_link = self._search(query, max, len(results), format)
            if not more_results:
                break
            results += more_results
        return results

    def _search(self, query, limit, offset, format):
        '''
        Returns a list of result objects, with the url for the next page bing search url.
        '''
        if isinstance(query, unicode):
            query = query.encode('utf8')
        url = self.QUERY_URL.format(urllib2.quote("'{}'".format(query)), limit, offset, format)
        r = requests.get(url, auth=("", self.api_key))
        try:
            json_results = r.json()
        except ValueError as vE:
            if not self.safe:
                raise PyBingException("Request returned with code %s, error msg: %s" % (r.status_code, r.text))
            else:
                print "[ERROR] Request returned with code %s, error msg: %s. \nContinuing in 5 seconds." % (r.status_code, r.text)
                time.sleep(5)
        try:
            next_link = json_results['d']['__next']
        except KeyError as kE:
            if not self.safe:
                raise PyBingException("Couldn't extract next_link: KeyError: %s" % kE)
            else:
                print "Couldn't extract next_link: KeyError: %s" % kE
                time.sleep(3)
            next_link = ''
        return [Result(single_result_json) for single_result_json in json_results['d']['results']], next_link


class PyBingNewsSearch(PyBingSearch):

    QUERY_URL = 'https://api.datamarket.azure.com/Bing/Search/v1/News?Query={}&$format={}'

    def __init__(self, api_key, safe=False, latest_window=7):
        self.api_key = api_key
        self.safe = safe
        self.latest_window = latest_window

    def search(self, query, format='json', aggregrate=False, **kwargs):
        ''' Returns the result list'''
        results, query_url = self._search(query, format=format, **kwargs)
        if aggregrate:
            return results
        else:
            results, query_url

    def search_all(self, query, format='json', limit=100, aggregrate=True, **kwargs):
        ''' Returns a single list containing up to 'limit' Result objects'''
        result_url_set = set()
        results = []
        raw_results, query_url = self._search(query, format, **kwargs)
        results.append(results, query_url)
        if not raw_results:
            return results
        current_url = raw_results[-1]['url']
        prev_url = None
        total_results = len(raw_results)
        while total_results <= limit:
            max = limit - total_results
            kwargs['$skip'] = total_results
            more_results, query_url = self._search(query, format=format, **kwargs)
            prev_url = current_url
            current_url = more_results[-1]['url']
            if prev_url == current_url:
                break
            selected_results = []
            for result in more_results:
                if result['Url'] not in result_url_set:
                    result_url_set.add(result['Url'])
                    selected_results.append(result)
            results.append((selected_results, query_url))
        if aggregrate:
            aggregrate_results = []
            for result, query_url in results:
                aggregrate_results += result
            return aggregrate_results
        else:
            return results

    def _search(self, query, format='json', **kwargs):
        url = self.QUERY_URL.format(urllib2.quote("'{}'".format(query)), 'json')
        r = requests.get(url, auth=("", self.api_key), params=kwargs)

        try:
            json_results = r.json()
        except ValueError as vE:
            if not self.safe:
                raise PyBingException("Request returned with code %s, error msg: %s" % (r.status_code, r.text))
            else:
                print "[ERROR] Request returned with code %s, error msg: %s. \nContinuing in 5 seconds." % (r.status_code, r.text)
                time.sleep(5)

        if format == 'json':
            results = json_results['d']['results']
        else:
            results = [Result(single_result_json) for single_result_json in json_results['d']['results']]
        return results, r.url

    def search_latest(self, query, format='json', aggregrate=True, **kwargs):
        result_url_set = set()
        before = kwargs.pop('before', None)
        if not before:
            before_date = datetime.date.today() - datetime.timedelta(days=self.latest_window)
        else:
            before_date = dateutil.parser.parse(before).date()

        kwargs['NewsSortBy'] = "'Date'"
        results = []
        current_url = None
        while True:
            kwargs['$skip'] = len(results)
            more_results, query_url = self._search(query, format=format, **kwargs)
            selected_results = []
            for result in more_results:
                date = result['Date']
                current_date = dateutil.parser.parse(date).date()
                if current_date < before_date and result['Url'] not in result_url_set():
                    result_url_set.add(result['Url'])
                    selected_results.append(result)
            prev_url = current_url
            current_url = more_results[-1]['Url']
            if prev_url == current_url:
                break
            results.append((selected_results, query_url))

        if aggregrate:
            aggregrate_results = []
            for result, query_url in results:
                aggregrate_results += result
            return aggregrate_results
        else:
            return results


class Result(object):
    '''
    The class represents a SINGLE search result.
    Each result will come with the following:

    #For the actual results#
    title: title of the result
    url: the url of the result
    description: description for the result
    id: bing id for the page

    #Meta info#:
    meta.uri: the search uri for bing
    meta.type: for the most part WebResult
    '''

    class _Meta(object):
        '''
        Holds the meta info for the result.
        '''
        def __init__(self, meta):
            self.type = meta['type']
            self.uri = meta['uri']

    def __init__(self, result):
        self.url = result['Url']
        self.title = result['Title']
        self.description = result['Description']
        self.id = result['ID']
        if 'Date' in result:
            self.date = result['Date']

        self.meta = self._Meta(result['__metadata'])

    def __getitem__(self, key):
        return getattr(self, key)
