import requests
import urllib.parse
import yt_dlp
from yt_dlp.utils import DateRange
import os
import sys
import re
from utils import upperescape, checkconfig, offsethandler, YoutubeDLLogger, ytdl_hooks, ytdl_hooks_debug, setup_logging  # NOQA
from datetime import datetime
import schedule
import time
import logging
import argparse

# allow debug arg for verbose logging
parser = argparse.ArgumentParser(description='Loads Configuration.')
parser.add_argument(
    '--debug',
    action='store_true',
    help='Enable debug logging'
)
args = parser.parse_args()

# setup logger
logger = setup_logging(True, True, args.debug)

date_format = "%Y-%m-%dT%H:%M:%SZ"
now = datetime.now()

CONFIGFILE = os.environ['CONFIGPATH']
CONFIGPATH = CONFIGFILE.replace('config.yml', '')
SCANINTERVAL = 60


class SonarrYTDL(object):

    def __init__(self):
        cfg = checkconfig()
        self.cfg_sonarrytdl(cfg)
        self.cfg_sonarr(cfg)
        self.cfg_series(cfg)
        self.cfg_ytdl(cfg)
        self.naming_format = self.get_naming_format()

    def cfg_sonarrytdl(self, cfg):
        """Loads main configuration

        Args:
            cfg (dict): Configuration File

        """

        try:
            self.set_scan_interval(cfg['sonarrytdl']['scan_interval'])
            try:
                self.debug = cfg['sonarrytdl']['debug'] in ['true', 'True']
                if self.debug:
                    logger.setLevel(logging.DEBUG)
                    for logs in logger.handlers:
                        if logs.name == 'FileHandler':
                            logs.setLevel(logging.DEBUG)
                        if logs.name == 'StreamHandler':
                            logs.setLevel(logging.DEBUG)
                    logger.debug('DEBUGGING ENABLED')
            except AttributeError:
                self.debug = False
        except Exception:
            sys.exit("Error with sonarrytdl config.yml values.")

    def cfg_sonarr(self, cfg):
        """Loads Sonarr configuration

        Args:
            cfg (dict): Configuration File

        """

        try:
            scheme = "http"
            if cfg['sonarr']['ssl'] in ['true', 'True']:
                scheme = "https"
            self.base_url = f"{scheme}://{cfg['sonarr']['host']}:{str(cfg['sonarr']['port'])}"
            self.api_key = cfg['sonarr']['apikey']
            self.mappings = cfg['sonarr']['rel-mappings']
        except Exception:
            sys.exit("Error with sonarr config.yml values.")

    def cfg_ytdl(self, cfg):
        """Loads YTDL configuration

        Args:
            cfg (dict): Configuration File

        """

        try:
            self.ytdl_format = cfg['ytdl']['default_format']
        except Exception:
            sys.exit("Error with ytdl config.yml values.")

    def cfg_series(self, cfg):
        """Loads Series configuration

        Args:
            cfg (dict): Configuration File

        """

        try:
            self.series = cfg["series"]
        except Exception:
            sys.exit("Error with series config.yml values.")

    def sonarr_response_handler(self, response):
        if response.status_code != 200:
            sys.exit('Issue communicating with sonarr!')
        elif response.status_code == 200:
            if isinstance(response.json(), list) or isinstance(response.json(), dict):
                return response.json()
            # If sonarr is available but doesn't return a list
            # This can happen when errors like disk space occur
            else:
                logger.debug(f'Error response received:\n {response.json()}')
                sys.exit('Sonarr available but error received.')

    def get_episodes_by_series_id(self, series_id):
        """Returns all episodes for the given series

        Args:
            series_id (int): Sonarr series id

        Returns:
            list: all episodes in the given series
        """

        logger.debug(f'Sonarr: Request episodes for series_id: {series_id}')
        args = {'seriesId': series_id}
        res = self.request_get(f"{self.base_url}/api/episode", args)
        return self.sonarr_response_handler(res)

    def get_naming_format(self):
        """Returns the file naming format for your collection

        Returns:
            Naming format as dictionary
        """
        logger.debug(f'Sonarr: Request naming format')
        res = self.request_get(f"{self.base_url}/api/v3/config/naming")
        return self.sonarr_response_handler(res)

    def get_series(self):
        """Return all series in your collection

        Returns:
            list: shows available in sonarr
        """
        logger.debug('Begin call Sonarr for all available series')
        res = self.request_get(f"{self.base_url}/api/series")
        return self.sonarr_response_handler(res)

    def request_get(self, url, params=None):
        """Wrapper on the requests.get

        Args:
            url (str): api that accepts put requests
            params (str, optional): additional url parameters. Defaults to None.

        Returns:
            Response: api response
        """
        logger.debug(f"Begin GET with url: {url}")
        args = {
            "apikey": self.api_key
        }
        if params is not None:
            logger.debug("Begin GET with params: {params}")
            args.update(params)
        url = f"{url}?{urllib.parse.urlencode(args)}"
        res = requests.get(url)
        return res

    def request_put(self, url, params=None, jsondata=None):
        """Wrapper on the requests.put

        Args:
            url (str): api that accepts put requests
            params (str, optional): additional url parameters. Defaults to None.
            jsondata (dict, optional): data to put to url. Defaults to None.

        Returns:
            Response: api response
        """
        logger.debug(f"Begin PUT with url: {url}")
        headers = {
            'Content-Type': 'application/json',
        }
        arguments = (
            ('apikey', self.api_key),
        )
        if params is not None:
            arguments.update(params)
            logger.debug(f"Begin PUT with params: {params}")
        res = requests.post(
            url,
            headers=headers,
            params=arguments,
            json=jsondata
        )
        return res

    def namefile(self, series, episode, quality):
        if self.naming_format['renameEpisodes']:
            foldername = self.naming_format['seasonFolderFormat']
            if '{season:00}' in foldername:
                foldername = foldername.replace('{season:00}', str(episode['seasonNumber']).zfill(2))
            elif '{season:0}' in foldername:
                foldername = foldername.replace('{season:0}', episode['seasonNumber'])
            filename = self.naming_format['standardEpisodeFormat']
            if '{season:00}' in filename:
                filename = filename.replace('{season:00}', str(episode['seasonNumber']).zfill(2))
            elif '{season:0}' in filename:
                filename = filename.replace('{season:0}', episode['seasonNumber'])
            if '{episode:00}' in filename:
                filename = filename.replace('{episode:00}', str(episode['episodeNumber']).zfill(2))
            elif '{episode:0}' in filename:
                filename = filename.replace('{episode:0}', episode['episodeNumber'])
            if '{Series Title}' in filename:
                filename = filename.replace('{Series Title}', series['title'])
            elif '{Series CleanTitle}' in filename:
                filename = filename.replace('{Series CleanTitle}', series['title'])
            elif '{Series TitleYear}' in filename:
                filename = filename.replace('{Series TitleYear}', series['title'] + ' (' + str(series['year']) + ')')
            elif '{Series CleanTitleYear}' in filename:
                filename = filename.replace('{Series CleanTitleYear}', series['title'] + ' (' + str(series['year']) + ')')
            if '{Episode Title}' in filename:
                filename = filename.replace('{Episode Title}', episode['title'])
            elif '{Episode CleanTitle}' in filename:
                filename = filename.replace('{Episode CleanTitle}', episode['title'])
            if '{Quality Title}' in filename:
                filename = filename.replace('{Quality Title}', quality)
            elif '{Quality Full}' in filename:
                filename = filename.replace('{Quality Full}', quality)
            filename = re.sub("\{.*?\}", '', filename)
            basename = filename + '.mp4'
        else:
            foldername = '.'
            basename = '{1} - S{0}E{2} - {3} {4}.mp4'.format(
                episode['seasonNumber'],
                series['title'],
                episode['episodeNumber'],
                episode['title'],
                quality)
        logger.debug(f"Folder: {foldername}\nFilename: {basename}")
        return foldername, basename


    def rescanseries(self, series_id):
        """Refresh series information from trakt and rescan disk

        Args:
            series_id (int): Sonarr series id

        Returns:
            response: Sonarr rescan series API response
        """

        logger.debug(f"Begin call Sonarr to rescan for series_id: {series_id}")
        data = {
            "name": "RescanSeries",
            "seriesId": str(series_id)
        }
        res = self.request_put(
            f"{self.base_url}/api/command",
            None,
            data
        )
        return res.json()

    def filterseries(self):
        """Return all series in Sonarr that are to be downloaded by youtube-dl

        Returns:
            dict: containing configuration values
        """

        series = self.get_series()
        matched = []
        for ser in series[:]:
            for mapping in self.mappings:
                if ser['path'].find(mapping['media-folder']) >= 0:
                    partition = ser['path'].partition(mapping['media-folder'])
                    if partition[0] == '' or partition[0] == os.sep:
                        ser['modpath'] = os.path.join(partition[0], mapping['relative-path'], partition[2])
            # print(ser['path'])
            # if ser['modpath'] is not None:
            #    print(ser['modpath'])
            for wnt in self.series:
                if wnt['title'] == ser['title']:
                    # Set default values
                    ser['subtitles'] = False
                    ser['playlistreverse'] = True
                    ser['subtitles_languages'] = ['en']
                    ser['subtitles_autogenerated'] = False
                    # Update values
                    if 'regex' in wnt:
                        regex = wnt['regex']
                        if 'sonarr' in regex:
                            ser['sonarr_regex'] = regex['sonarr']
                        if 'site' in regex:
                            ser['site_regex_match'] = regex['site']['match']
                            ser['site_regex_replace'] = regex['site']['replace']
                    if 'offset' in wnt:
                        ser['offset'] = wnt['offset']
                    if 'ignore_daterange' in wnt:
                        try:
                            if str(wnt['ignore_daterange']).lower() in ['true', 't', 'y', 'yes']:
                                ser['ignore_daterange'] = True
                        except Exception:
                            ser['ignore_daterange'] = False
                    else:
                        ser['ignore_daterange'] = False
                    if 'cookies_file' in wnt:
                        ser['cookies_file'] = wnt['cookies_file']
                    if 'format' in wnt:
                        ser['format'] = wnt['format']
                    if 'playlistreverse' in wnt:
                        if wnt['playlistreverse'] == 'False':
                            ser['playlistreverse'] = False
                    if 'subtitles' in wnt:
                        ser['subtitles'] = True
                        if 'languages' in wnt['subtitles']:
                            ser['subtitles_languages'] = wnt['subtitles']['languages']
                        if 'autogenerated' in wnt['subtitles']:
                            ser['subtitles_autogenerated'] = wnt['subtitles']['autogenerated']
                    ser['url'] = wnt['url']
                    matched.append(ser)
        for check in matched:
            if not check['monitored']:
                logger.warning(f"{ser['title']} is not currently monitored")
        del series[:]
        return matched

    def getseriesepisodes(self, series):
        """ Gets episodes for a series where they are in the configuration file and exists in sonarr.
            It only will get episodes that are monitored and dont have a file already.

        Args:
            series (list): list of series to get episodes for

        Returns:
            list: missing monitored episodes episodes
        """

        needed = []
        for ser in series[:]:
            episodes = self.get_episodes_by_series_id(ser['id'])
            for eps in episodes[:]:
                eps_date = now
                # remove episodes that dont have the monitored flag
                if not eps['monitored']:
                    episodes.remove(eps)
                    continue
                # remove if already downloaded
                if eps['hasFile']:
                    episodes.remove(eps)
                    continue
                # remove if no airdate, these are tbc
                if "airDateUtc" in eps:
                    eps_date = datetime.strptime(eps['airDateUtc'], date_format)
                    # remove if airdate in future
                    if eps_date > now:
                        episodes.remove(eps)
                        continue
                    # add any offsets
                    if 'offset' in ser:
                        eps_date = offsethandler(eps_date, ser['offset'])
                    # Apply any regex to episode title
                    if 'sonarr_regex' in ser:
                        try:
                            for regex in ser['sonarr_regex']:
                                match = regex['match']
                                replace = regex['replace']
                                logger.debug(f"Updating episode title '{eps['title']}' with regex '{match}' and replacement '{replace}'")
                                eps['title'] = re.sub(match, replace, eps['title'])
                                logger.debug(f"New title '{eps['title']}'")
                        except TypeError:
                            logger.error(f"{ser['title']} has invalid settings for sonarr regex")
                else:
                    episodes.remove(eps)
                    continue
                needed.append(eps)
            # If no episodes needed remove series
            if len(episodes) == 0:
                logger.info(f"{ser['title']} no episodes needed")
                series.remove(ser)
            else:
                logger.info(f"{ser['title']} missing {len(episodes)} episodes")
                for i, e in enumerate(episodes):
                    logger.info(f"  {i + 1}: {ser['title']} - {e['title']}")
        return needed

    def appendcookie(self, ytdlopts, cookies=None):
        """Checks if specified cookie file exists in config

        Args:
            ytdlopts (dict): Youtube-dl options to append cookie to
            cookies (str, optional): path to cookie file. Defaults to None.

        Returns:
            dict: Youtube-dl options
                original if problem with cookies file
                updated with cookies value if cookies file exists
        """
        if cookies is not None:
            cookie_path = os.path.abspath(CONFIGPATH + cookies)
            cookie_exists = os.path.exists(cookie_path)
            if cookie_exists is True:
                ytdlopts.update({
                    'cookiefile': cookie_path
                })
                # if self.debug is True:
                logger.debug(f"  Cookies file used: {cookie_path}")
            if cookie_exists is False:
                logger.warning("  cookie files specified but doesn't exist.")
            return ytdlopts
        else:
            return ytdlopts

    def customformat(self, ytdlopts, customformat=None):
        """Checks if specified cookie file exists in config
        - ``ytdlopts``: Youtube-dl options to change the ytdl format for
        - ``customformat``: format to download
        returns:
            ytdlopts
                original: if no custom format
                updated: with new format value if customformat exists
        """
        if customformat is not None:
            ytdlopts.update({
                'format': customformat
            })
            return ytdlopts
        else:
            return ytdlopts

    def ytdl_eps_search_opts(self, regextitle, playlistreverse, cookies=None, daterange=None):
        """Generates the Youtube DL options for searching a specific episode in a playlist

        Args:
            regextitle (str): Regex to use to match the episode name in youtube
            playlistreverse (bool): Search playlist videos in reverse order
            cookies (str, optional): cookie file location. Defaults to None.
            daterange (dict, optional): dict containing ytdl DateRange.

        Returns:
            dict: Youtube DL options
        """

        ytdlopts = {
            'ignoreerrors': True,
            'playlistreverse': playlistreverse,
            'matchtitle': regextitle,
            'quiet': True,
        }
        if daterange:
            ytdlopts.update({
                'daterange': daterange['daterange']
            })
        if self.debug is True:
            ytdlopts.update({
                'quiet': False,
                'logger': YoutubeDLLogger(),
                'progress_hooks': [ytdl_hooks],
            })
        ytdlopts = self.appendcookie(ytdlopts, cookies)
        if self.debug is True:
            logger.debug('Youtube-DL opts used for episode matching')
            logger.debug(ytdlopts)
        return ytdlopts

    def ytsearch(self, ydl_opts, playlist):
        """Search a playlist, channel or direct link using youtube dl match title regex.

        Args:
            ydl_opts (dict): contains basic youtube dl options to search with
            playlist (str): a youtube url to search

        Returns:
            (bool): True if found, False if not.
            (dict): Matched video result.
        """

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(
                    playlist,
                    download=False
                )
                # Handle no results returned (possible deleted channel or issue with cookies)
                if result is None:
                    logger.error(f"url {playlist} returned no videos, please check config.")
                    return False, ''
        except Exception as e:
            logger.error(e)
        else:
            video_url = None
            # Handle playlists and return first url
            if 'entries' in result and len(result['entries']) > 0:
                try:
                    video_url = result['entries'][0].get('webpage_url')
                except Exception as e:
                    logger.error(e)
            else:
                video_url = result.get('webpage_url')
            # Handle singular urls
            if playlist == video_url:
                logger.debug('Matched with original url')
                return True, result
            # If no urls returned
            if video_url is None:
                logger.error('No video_url')
                return False, ''
            # Assume all is good
            return True, result

    def download(self, series, episodes):
        if len(series) != 0:
            logger.info("Processing Wanted Downloads")
            # Loop through Sonarr Wanted Series
            wanted_series = [e['seriesId'] for e in episodes]
            for _, ser in enumerate(series):
                # This may be redundant as we filter it with episodes
                if ser['id'] not in wanted_series:
                    continue
                logger.info(f"  {ser['title']}:")
                # Get a list of entries in the url for the series from config
                with yt_dlp.YoutubeDL({"extract_flat": True, "quiet": (not self.debug)}) as ydl:
                    logger.info(f"    Extracting urls from {ser['url']}")
                    playlist_dict = ydl.extract_info(ser['url'], download=False)
                    logger.debug(f"    Extracted {len(playlist_dict['entries'])} entries")
                # Loop wanted episodes
                for e, eps in enumerate(episodes):
                    if ser['id'] == eps['seriesId']:
                        urls = []
                        # Regex Match on the playlist names
                        for video in playlist_dict["entries"]:
                            x = re.match(upperescape(eps['title']), video['title'], flags=re.IGNORECASE)
                            if None is not x:
                                urls.append(video['url'])
                        # Do we use a daterange to match?
                        YDL_daterange = None
                        try:
                            if not ser['ignore_daterange']:
                                airDate = datetime.strptime(eps['airDate'], '%Y-%m-%d')
                                YDL_daterange = {'daterange': DateRange((offsethandler(airDate, {'days': '-1'})).strftime("%Y%m%d"), (offsethandler(airDate, {'days': '1'})).strftime("%Y%m%d"))}
                        except KeyError:
                            # Not possible but handle missing airDates
                            logger.warning(f"    {e + 1}: Failure:Airdate Missing - {eps['title']}:")
                        # Do we pass cookies to get the videos?
                        cookies = None
                        if 'cookies_file' in ser:
                            cookies = ser['cookies_file']
                        ydleps = self.ytdl_eps_search_opts(upperescape(eps['title']), ser['playlistreverse'], cookies, YDL_daterange)
                        # Pass into downloader to match, daterange should help match the correct if there is multiple
                        for url in urls:
                            found, result = self.ytsearch(ydleps, url)
                            if found:
                                logger.info(f"    {e + 1}: Found - {eps['title']}:")
                                quality = 'WEBDL'
                                if result.get('height') in (2160, 1080, 720, 480):
                                    quality = f"WEBDL-{result['height']}p"
                                foldername, basename = self.namefile(ser, eps, quality)
                                if foldername != '.':
                                    os.makedirs(foldername, exist_ok=True)
                                    basename = os.path.join(foldername, basename)
                                usedpath = os.path.normpath('/sonarr_root' + os.sep + ser['path'])
                                if ser['modpath'] is not None:
                                    usedpath = os.path.normpath('/sonarr_root' + os.sep + ser['modpath'])
                                os.makedirs(usedpath, exist_ok=True)
                                ytdl_format_options = {
                                    'format': self.ytdl_format,
                                    'quiet': True,
                                    'merge-output-format': 'mp4',
                                    'outtmpl': usedpath + os.sep + basename,
                                    'progress_hooks': [ytdl_hooks],
                                    'noplaylist': True,
                                }
                                ytdl_format_options = self.appendcookie(ytdl_format_options, cookies)
                                if 'format' in ser:
                                    ytdl_format_options = self.customformat(ytdl_format_options, ser['format'])
                                if 'subtitles' in ser:
                                    if ser['subtitles']:
                                        postprocessors = []
                                        postprocessors.append({
                                            'key': 'FFmpegSubtitlesConvertor',
                                            'format': 'srt',
                                        })
                                        postprocessors.append({
                                            'key': 'FFmpegEmbedSubtitle',
                                        })
                                        autosubs = str(ser['subtitles_autogenerated']).lower() in ['true', 't', 'y', 'yes']
                                        ytdl_format_options.update({
                                            'writesubtitles': True,
                                            'writeautomaticsub': autosubs,
                                            'subtitleslangs': ser['subtitles_languages'],
                                            'postprocessors': postprocessors,
                                        })
                                if self.debug is True:
                                    ytdl_format_options.update({
                                        'quiet': False,
                                        'logger': YoutubeDLLogger(),
                                        'progress_hooks': [ytdl_hooks_debug],
                                    })
                                    logger.debug('Youtube-DL opts used for downloading')
                                    logger.debug(ytdl_format_options)
                                try:
                                    logger.info(f"      Downloading - {eps['title']}")
                                    with yt_dlp.YoutubeDL(ytdl_format_options) as ydl:
                                        # ydl.download([dlurl])
                                        ydl.download(result['webpage_url'])
                                    self.rescanseries(ser['id'])
                                    logger.info(f"      Downloaded - {eps['title']}")
                                except Exception as e:
                                    logger.error(f"      Failed - {eps['title']} - {e}")
                            else:
                                logger.info(f"    {e + 1}: Missing - {eps['title']}:")
        else:
            logger.info("Nothing to process")

    def set_scan_interval(self, interval):
        """ Changes the SCANINTERVAL if it is different that the default 60 Minutes
        Args:
            interval (int): Minutes to set SCANINTERVAL to.
        """

        global SCANINTERVAL
        if interval != SCANINTERVAL:
            SCANINTERVAL = interval
            logger.info(f"Scan interval set to every {interval} minutes by config.yml")
        else:
            logger.info(f"Default scan interval of every {interval} minutes")
        return


def main():
    client = SonarrYTDL()
    series = client.filterseries()
    episodes = client.getseriesepisodes(series)
    client.download(series, episodes)
    logger.info('Waiting...')


if __name__ == "__main__":
    logger.info('Initial run')
    main()
    schedule.every(int(SCANINTERVAL)).minutes.do(main)
    while True:
        schedule.run_pending()
        time.sleep(1)
