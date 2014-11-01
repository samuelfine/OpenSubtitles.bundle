# opensubtitles.org
# Subtitles service allowed by www.OpenSubtitles.org
# Language codes: http://www.opensubtitles.org/addons/export_languages.php

import difflib

OS_API = 'http://plexapp.api.opensubtitles.org/xml-rpc'
OS_PLEX_USERAGENT = 'plexapp.com v9.0'
SUBTITLE_EXT = ['utf','utf8','utf-8','sub','srt','smi','rt','ssa','aqt','jss','ass','idx']

####################################################################################################
def Start():

  HTTP.CacheTime = CACHE_1DAY
  HTTP.Headers['User-Agent'] = OS_PLEX_USERAGENT

  if 'quotaReached' not in Dict:

    Dict['quotaReached'] = int(Datetime.TimestampFromDatetime(Datetime.Now())) - (24*60*60)
    Dict.Save()

####################################################################################################
def opensubtitlesProxy():

  proxy = XMLRPC.Proxy(OS_API)
  username = Prefs['username'] if Prefs['username'] else ''
  password = Prefs['password'] if Prefs['password'] else ''

  token = proxy.LogIn(username, password, 'en', OS_PLEX_USERAGENT)['token']

  return (proxy, token)

####################################################################################################
def fetchSubtitles(proxy, token, part, imdbID=''):

  langList = list(set([Prefs['langPref1'], Prefs['langPref2'], Prefs['langPref3']]))
  langList.remove('None')

  # Remove all subs from languages no longer set in the agent's prefs
  for l in part.subtitles:
    if l not in langList:
      part.subtitles[l].validate_keys([])

  for l in langList:

    Log('Looking for match for GUID %s and size %d' % (part.openSubtitleHash, part.size))
    subtitleResponse = proxy.SearchSubtitles(token,[{'sublanguageid':l, 'moviehash':part.openSubtitleHash, 'moviebytesize':str(part.size)}])['data']
    #Log('hash/size search result: ')
    #Log(subtitleResponse)

    if subtitleResponse == False and imdbID != '': #let's try the imdbID, if we have one...

      subtitleResponse = proxy.SearchSubtitles(token,[{'sublanguageid':l, 'imdbid':imdbID}])['data']
      Log('Found nothing via hash, trying search with imdbid: ' + imdbID)
      #Log(subtitleResponse)

    if subtitleResponse != False:

      for st in subtitleResponse: #remove any subtitle formats we don't recognize

        if st['SubFormat'] not in SUBTITLE_EXT:
          Log('Removing a subtitle of type: ' + st['SubFormat'])
          subtitleResponse.remove(st)

      st = sorted(subtitleResponse, key=lambda k: int(k['SubDownloadsCnt']), reverse=True) #most downloaded subtitle file for current language

      filename = part.file.rsplit('/',1)[-1]
      lastScore = float(0.0)

      for sub in st:

        score = difflib.SequenceMatcher(None, sub['SubFileName'], filename).ratio()
        Log('Comparing "%s" vs. "%s" and it had the ratio: %f' % (sub['SubFileName'], filename, score))

        if score >= 0.6:

          if lastScore < score:
            Log('Choosing sub "%s" that scored %f' % (sub['SubFileName'], score))
            st = sub
            lastScore = score

        else:
          st = sorted(subtitleResponse, key=lambda k: int(k['SubDownloadsCnt']), reverse=True)[0]

      subUrl = st['SubDownloadLink'].rsplit('/sid-',1)[0]

      # Download subtitle only if it's not already present
      if subUrl not in part.subtitles[Locale.Language.Match(st['SubLanguageID'])]:

        subGz = HTTP.Request(subUrl, headers={'Accept-Encoding':'gzip'})
        downloadQuota = int(subGz.headers['Download-Quota'])

        if downloadQuota > 0:

          subData = Archive.GzipDecompress(subGz.content)
          part.subtitles[Locale.Language.Match(st['SubLanguageID'])][subUrl] = Proxy.Media(subData, ext=st['SubFormat'])
          Log('Download quota: %d' % (downloadQuota))

        else:
          Dict['quotaReached'] = int(Datetime.Now())

      else:
        Log('Skipping, subtitle already downloaded (%s)' % (subUrl))

    else:
      Log('No subtitles available for language ' + l)

####################################################################################################
class OpenSubtitlesAgentMovies(Agent.Movies):

  name = 'OpenSubtitles.org'
  languages = [Locale.Language.NoLanguage]
  primary_provider = False
  contributes_to = ['com.plexapp.agents.imdb']

  def search(self, results, media, lang):

    if Dict['quotaReached'] > int(Datetime.TimestampFromDatetime(Datetime.Now())) - (24*60*60):

      Log('24 hour download quota has been reached')
      return None

    results.Append(MetadataSearchResult(
      id    = media.primary_metadata.id.strip('t'),
      score = 100
    ))

  def update(self, metadata, media, lang):

    (proxy, token) = opensubtitlesProxy()

    for i in media.items:
      for part in i.parts:
        fetchSubtitles(proxy, token, part, metadata.id)

####################################################################################################
class OpenSubtitlesAgentTV(Agent.TV_Shows):

  name = 'OpenSubtitles.org'
  languages = [Locale.Language.NoLanguage]
  primary_provider = False
  contributes_to = ['com.plexapp.agents.thetvdb']

  def search(self, results, media, lang):

    if Dict['quotaReached'] > int(Datetime.TimestampFromDatetime(Datetime.Now())) - (24*60*60):

      Log('24 hour download quota has been reached')
      return None

    results.Append(MetadataSearchResult(
      id    = 'null',
      score = 100
    ))

  def update(self, metadata, media, lang):

    (proxy, token) = opensubtitlesProxy()

    for s in media.seasons:
      # just like in the Local Media Agent, if we have a date-based season skip for now.
      if int(s) < 1900:
        for e in media.seasons[s].episodes:
          for i in media.seasons[s].episodes[e].items:
            for part in i.parts:
              fetchSubtitles(proxy, token, part)
