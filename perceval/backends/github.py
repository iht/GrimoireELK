#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Bugzilla tickets for Elastic Search
#
# Copyright (C) 2015 Bitergia
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# Authors:
#   Alvaro del Castillo San Felix <acs@bitergia.com>
#

'''GitHub backend for Perseval'''

import json
import logging
import os
import requests

from perceval.backends.backend import Backend
from perceval.utils import get_eta, remove_last_char_from_file

class GitHub(Backend):

    _name = "github"
    users = {}

    def __init__(self, owner, repository, auth_token, 
                 cache = False, history = False):
        self.owner = owner
        self.repository = repository
        self.auth_token = auth_token
        self.pull_requests = []  # All pull requests from github repo
        self.cache = {}  # cache for pull requests
        self.use_cache = cache
        self.use_history = history
        self.url = self._get_url()


        # Create storage dir if it not exists
        dump_dir = self._get_storage_dir()
        if not os.path.isdir(dump_dir):
            os.makedirs(dump_dir)

        if self.use_cache:
            # Don't use history data. Will be generated from cache.
            self.use_history = False

        if self.use_history:
            self._restore()  # Load history

        else:
            if self.use_cache:
                logging.warning("Getting all data from cache.")
                try:
                    self._load_cache()
                    logging.debug("Cache loaded correctly")
                except:
                    # If any error loading the cache, clean it
                    self.use_cache = False
                    self._clean_cache()
            else:
                self._clean_cache()  # Cache will be refreshed

    def _get_url(self):
        github_per_page = 30  # 100 in other items. 20 for pull requests. 30 issues
        github_api = "https://api.github.com"
        github_api_repos = github_api + "/repos"
        url_repo = github_api_repos + "/" + self.owner +"/" + self.repository

        url_pulls = url_repo + "/pulls"
        url_issues = url_repo + "/issues"

        url_params = "?per_page=" + str(github_per_page)
        url_params += "&state=all"  # open and close pull requests
        url_params += "&sort=updated"  # sort by last updated
        url_params += "&direction=asc"  # first older pull request

        # prs_count = getPullRequests(url_pulls+url_params)
        url = url_issues + url_params

        return url


    def _restore(self):
        '''Restore JSON full data from storage '''

        restore_dir = self._get_storage_dir()

        if os.path.isdir(restore_dir):
            try:
                logging.debug("Restoring data from %s" % restore_dir)
                restore_file = os.path.join(restore_dir, "pull_requests.json")
                if os.path.isfile(restore_file):
                    with open(restore_file) as f:
                        data = f.read()
                        self.issues = json.loads(data)
                logging.debug("Restore completed")
            except ValueError:
                logging.warning("Restore failed. Wrong dump files in: %s" %
                                restore_file)


    def _dump(self):
        ''' Dump JSON full data to storage '''

        dump_dir = self._get_storage_dir()

        logging.debug("Dumping data to  %s" % dump_dir)
        dump_file = os.path.join(dump_dir, "pull_requests.json")
        with open(dump_file, "w") as f:
            f.write(json.dumps(self.pull_requests))
        logging.debug("Dump completed")


    def fetch(self):
        ''' Returns an iterator for the data gathered '''

        return self.getIssuesPullRequests()

    def _get_name(self):

        return GitHub._name


    def get_id(self):

        _id = "_%s_%s" % (self.owner, self.repository)

        return _id.lower()


    def _clean_cache(self):
        cache_files = ["cache_pull_requests.json"]

        for name in cache_files:
            fname = os.path.join(self._get_storage_dir(), name)
            with open(fname,"w") as f:
                f.write("[]")  # Empty array = empty cache

        cache_keys = ['pull_requests']

        for _id in cache_keys:
            self.cache[_id] = []

    def _close_cache(self):
        ''' Remove last , in arrays in JSON files '''
        cache_files = ["cache_pull_requests.json"]

        for name in cache_files:
            fname = os.path.join(self._get_storage_dir(), name)
            # Remove ,] and add ]
            remove_last_char_from_file(fname)
            remove_last_char_from_file(fname)
            with open(fname,"a") as f:
                f.write("]")


    def getLastUpdateFromES(self, _type):

        last_update = self.elastic.get_last_date(_type, 'updated_at')

        return last_update

    def _pull_requests_to_cache(self, pull_requests):
        ''' Append to pull request JSON cache '''

        cache_file = os.path.join(self._get_storage_dir(),
                                  "cache_pull_requests.json")
        remove_last_char_from_file(cache_file)

        checked_prs = []

        for pull in pull_requests:
            if not 'head' in pull.keys() and not 'pull_request' in pull.keys():
                # And issue that it is not a PR
                continue
            else: 
                checked_prs.append(pull)

        with open(cache_file, "a") as cache:
            data_json = json.dumps(checked_prs)
            cache.write(data_json)
            cache.write(",")  # array of issues delimiter
            cache.write("]")  # close the JSON array



    def getUser(self, url, login):

        if login not in GitHub.users:

            url = url + "/users/" + self.login

            r = requests.get(url, verify=False,
                             headers={'Authorization':'token ' + self.auth_token})
            user = r.json()

            GitHub.users[self.login] = user

            # Get the public organizations also
            url += "/orgs"
            r = requests.get(url, verify=False,
                             headers={'Authorization':'token ' + self.auth_token})
            orgs = r.json()

            GitHub.users[self.login]['orgs'] = orgs


    def getPullRequests(self, url):
        url_next = url
        prs_count = 0
        last_page = None
        page = 1

        url_next += "&page="+str(page)

        while url_next:
            logging.info("Get issues pulls requests from " + url_next)
            r = requests.get(url_next, verify=False,
                             headers={'Authorization':'token ' +
                                      self.auth_token})
            pulls = r.json()
            self.pull_requests += pulls
            self._dump()
            self._pull_requests_to_cache (pulls)
            prs_count += len(pulls)

            logging.info(r.headers['X-RateLimit-Remaining'])

            url_next = None
            if 'next' in r.links:
                url_next = r.links['next']['url']  # Loving requests :)

            if not last_page:
                last_page = r.links['last']['url'].split('&page=')[1].split('&')[0]

            logging.info("Page: %i/%s" % (page, last_page))

            page += 1

        self._close_cache()

        return self

    def getIssuesPullRequests(self):
        _type = "issues_pullrequests"
        prs_count = 0
        last_page = page = 1
        # last_update = self.getLastUpdateFromES(_type)
        last_update = None  # broken order in github API
        if last_update is not None:
            logging.info("Getting issues since: " + last_update)
            self.url += "&since="+last_update
        url_next = self.url

        while url_next:
            logging.info("Get issues pulls requests from " + url_next)
            r = requests.get(url_next, verify=False,
                             headers={'Authorization':'token ' + self.auth_token})
            pulls = r.json()
            self.pull_requests += pulls
            self._dump()
            self._pull_requests_to_cache(pulls)
            prs_count += len(pulls)

            logging.info(r.headers['X-RateLimit-Remaining'])

            url_next = None
            if 'next' in r.links:
                url_next = r.links['next']['url']  # Loving requests :)

            if last_page == 1:
                if 'last' in r.links:
                    last_page = r.links['last']['url'].split('&page=')[1].split('&')[0]

            logging.info("Page: %i/%s" % (page, last_page))

            page += 1

        self._close_cache()

        return self

    # Iterator
    def __iter__(self):

        self.iter = 0
        return self

    def __next__(self):

        if self.iter == len(self.pull_requests):
            raise StopIteration
        item = self.issues[self.pull_requests]

        self.iter += 1

        return item
