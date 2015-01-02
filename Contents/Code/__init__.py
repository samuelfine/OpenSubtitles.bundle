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
  
  ## Check for missing token
  if 'proxy_token' not in Dict:
    ## Perform login
    Log('No valid token in Dict.')
    (success, token) = proxyLogin(proxy, username, password)
    if success:
      Dict['proxy_token'] = token
      return (proxy, token)
    else:
      Dict['proxy_token'] = ''
      return (proxy, '')
  else:
    ## Token already exists, check if it's still valid
    Log('Existing token found. Revalidating.')
    if Dict['proxy_token'] != '' and checkToken(proxy, Dict['proxy_token']):
      return (proxy, Dict['proxy_token'])
    else:
      ## Invalid token. Re-authenticate.
      (success, token) = proxyLogin(proxy, username, password)
      if success:
        Dict['proxy_token'] = token
        return (proxy, token)
      else:
        return (proxy, '')

####################################################################################################
def proxyLogin(proxy, username, password):
  token = proxy.LogIn(username, password, 'en', OS_PLEX_USERAGENT)['token']
  if checkToken(proxy, token):
    Log('Successfull login.')
    return (True, token)
  else:
    Log('Unsuccessful login.')
    return (False, '')
  
####################################################################################################
def checkToken(proxy, token):
  try:
    proxyCheck = proxy.NoOperation(token)
    if proxyCheck['status'] == '200 OK':
      Log('Valid token.')
      return True
    else:
      Log('Invalid Token.')
      return False
  except:
    Log('Error occured when checking token.')
    return False

####################################################################################################
def fetchSubtitles(proxy, token, part, imdbID=''):

  langList = list(set([Prefs['langPref1'], Prefs['langPref2'], Prefs['langPref3']]))
  if 'None' in langList:
    langList.remove('None')

  # Remove all subs from languages no longer set in the agent's prefs
  langListAlt = [Locale.Language.Match(l) for l in langList] # ISO 639-2 (from agent's prefs) --> ISO 639-1 (used to store subs in PMS)

  for l in part.subtitles:
    if l not in langListAlt:
      part.subtitles[l].validate_keys([])

  for l in langList:

    subtitleResponse = False

    if part.openSubtitleHash != '':

      Log('Looking for match for GUID %s and size %d' % (part.openSubtitleHash, part.size))
      subtitleResponse = proxy.SearchSubtitles(token,[{'sublanguageid':l, 'moviehash':part.openSubtitleHash, 'moviebytesize':str(part.size)}])['data']
      #Log('hash/size search result: ')
      #Log(subtitleResponse)

    if subtitleResponse == False and imdbID != '': #let's try the imdbID, if we have one...

      Log('Found nothing via hash, trying search with imdbid: ' + imdbID)
      subtitleResponse = proxy.SearchSubtitles(token,[{'sublanguageid':l, 'imdbid':imdbID}])['data']
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

        try:
          subGz = HTTP.Request(subUrl, headers={'Accept-Encoding':'gzip'})
          downloadQuota = int(subGz.headers['Download-Quota'])
        except Ex.HTTPError, e:
          if e.code == 407:
            Log('24 hour download quota has been reached')
            Dict['quotaReached'] = int(Datetime.TimestampFromDatetime(Datetime.Now()))
            return None
        except:
          return None

        if downloadQuota > 0:

          subData = Archive.GzipDecompress(subGz.content)
          part.subtitles[Locale.Language.Match(st['SubLanguageID'])][subUrl] = Proxy.Media(subData, ext=st['SubFormat'])
          Log('Download quota: %d' % (downloadQuota))

        else:
          Dict['quotaReached'] = int(Datetime.TimestampFromDatetime(Datetime.Now()))

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
    if token != '':
      for i in media.items:
        for part in i.parts:
          fetchSubtitles(proxy, token, part, metadata.id)
    else: 
      Log('Unable to retrieve valid token. Skipping')

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
    if token != '':
      for s in media.seasons:
        # just like in the Local Media Agent, if we have a date-based season skip for now.
        if int(s) < 1900:
          for e in media.seasons[s].episodes:
            for i in media.seasons[s].episodes[e].items:
              for part in i.parts:
                fetchSubtitles(proxy, token, part)
