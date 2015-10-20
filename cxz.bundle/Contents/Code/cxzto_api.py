# -*- coding: utf-8 -*-

####################################################################################################
# 
# This work is licensed under a Creative Commons Attribution 3.0 Unported License.
# See http://creativecommons.org/licenses/by/3.0/deed.en_US for detail.
#
####################################################################################################

import urllib2
import urllib
import json
import time
import re
from random import randint

CXZTO_URL = 'http://cxz.to'
AJAX_REQUEST = CXZTO_URL + '/%s/i%s-zzz.html?ajax&id=%s&download=1&view=1&view_embed=0&blocked=0&folder_quality=null&folder_lang=null&folder_translate=null&folder=%s'
ITEM_SEARCH = CXZTO_URL + '/video/%s/search.aspx?search=%s'

class API(object):
    def __init__(self):
        self.items = {}

    ####################################################################################################
    def api_request(self, action, params={}, url=CXZTO_URL, timeout=600, disableHTTPHandler=False, cacheTime=3600):
        error_msg = {
            'status': 400,
            'name': 'Bad Requiest',
            'message': 'Bad Requiest',
            'code': 0,
        }
        if 'types' == action:
            return self.requestTypes(params)

        if 'items' == action:
            if params.get('query'):
                return self.requestSearchItems(params)
            return self.requestItems(params)

        if action.startswith('items/'):
            itemId = action.split('/')[-1] # last elem
            return self.requestItem(itemId, params)

        if 'genres' == action:
            return self.requestGenres(params)

        if action.startswith('folder/'):
            parts = action.split('/')
            return self.requestFolder(parts[1], parts[2], parts[3])

        return error_msg
    ####################################################################################################
    def requestTypes(self, params):
        return {
            'status': 200,
            'message': 'OK',
            'items': [
                {'title':'Фильмы', 'id':'films', 'genre_id':'film_genre'}, 
                {'title':'Сериалы', 'id':'serials', 'genre_id':'genre'},
                {'title':'Мультфильмы', 'id':'cartoons', 'genre_id':'cartoon_genre'},
                {'title':'Мультсериалы', 'id':'cartoonserials', 'genre_id':'genre'},
                {'title':'ТВ', 'id':'tvshow', 'genre_id':'tv_genre'},
                ]
        }

    ####################################################################################################
    def requestGenres(self, params):
        try:
            fullPageUrl = '%s/%s/group/%s' % (CXZTO_URL, params['type'], params['genre_id'])
            fullPage = HTML.ElementFromURL(fullPageUrl)
            itemsElem = fullPage.xpath('//ul[@class="b-list-links"]/li/a')
            genres = []
            for elem in itemsElem:
                value = elem.attrib['href']
                if 'genre' in value:
                    genre = {}
                    genre['title'] = elem.text_content()
                    genre['id'] = value.rstrip('/').split('/')[-1]
                    genres.append(genre)

            return {
                'status': 200,
                'items': genres,
            }
        except:
            Log.Exception('Error querying genres')
            return {
                'status': 500,
                'message': '',
            }
    ####################################################################################################
    def requestItem(self, itemId, params):
        # Yeah, I know that keeping a state is not so good for this, but this entire code is a quick hack. :)
        item = self.items[itemId]
        return {
            'status': 200,
            'item': item
        }

    ####################################################################################################
    def requestSearchItems(self, params):
        try:
            userQuery = params['query']
            # looks like no pagination in search results. Weird.
            #if 'page' in params:
            #    urlQuery['page'] = params['page'] 

            fullPageUrl = ITEM_SEARCH % (params['type'], userQuery)
            return self.requestItemsForUrl(fullPageUrl, params, '//div[@class="b-search-page__results"]/a')
        except:
            Log.Exception('Error querying search items')
            return {'status':500, 'items':[]}

    ####################################################################################################
    def requestItems(self, params):
        try:
            itemType = params['type']
            urlQuery = {}
            urlQuery['page'] = params['page'] if 'page' in params else 0
            urlQuery['sort'] = params['sort'] if 'sort' in params else 'new'

            queryString = urllib.urlencode(urlQuery)
            fullPageUrl = ''
            if 'genre' in params:
                fullPageUrl = '%s/%s/%s/%s/?%s' % (CXZTO_URL, itemType, params['genre_id'], params['genre'], queryString)
            else:
                fullPageUrl = '%s/%s/?%s' % (CXZTO_URL, itemType, queryString)

            return self.requestItemsForUrl(fullPageUrl, params, '//a[@class="b-poster-tile__link"]')
        except:
            Log.Exception('Error querying items')
            return {'status':500, 'items':[]}

    ####################################################################################################
    def requestItemsForUrl(self, fullPageUrl, params, itemXPathQuery):
        self.items = {}
        items = []
        fullPage = HTML.ElementFromURL(fullPageUrl)
        itemsElem = fullPage.xpath(itemXPathQuery)
        itemType = params['type']

        @parallelize
        def loadItems():
            for itemElem in itemsElem:
                @task
                def loadItemTask(itemElem=itemElem, items=items):
                    # search items has 'style' attrib
                    if 'style' in itemElem.attrib:
                        # ignore if item has 'display: none' set
                        if len(itemElem.attrib['style'].strip()) > 0:
                            return
                    item = {}
                    itemUrl = itemElem.attrib['href']
                    item['id'] = self.fetchItemIdFromUrl(itemUrl)
                    item['type'] = itemType
                    item['poster'] = self.fetchItemPoster(itemUrl, itemElem)

                    itemPageUrl = CXZTO_URL + itemUrl
                    itemFullPage = HTML.ElementFromURL(itemPageUrl)

                    title = itemFullPage.xpath('//div[@class="b-tab-item__title-inner"]/span')[0].text_content()
                    item['title'] = title.strip() 

                    originalTitleElem = itemFullPage.cssselect('.b-tab-item__title-origin')
                    originalTitle = None
                    if len(originalTitleElem):
                        originalTitle = originalTitleElem[0].text_content().strip()

                    # first try long description, which is inside '<p>', to avoid including 'expand/collapse' text
                    plotElem = itemFullPage.xpath('//div[@class="b-tab-item__description"]/p')
                    if len(plotElem) == 0:
                        # then short
                        plotElem = itemFullPage.xpath('//div[@class="b-tab-item__description"]')

                    plot = plotElem[0].text_content().strip()
                    if originalTitle:
                        plot = originalTitle + '\r\n' + plot
                    item['plot'] = plot

                    item['year'] = self.fetchYear(itemFullPage, itemUrl, itemType)
                    item['countries'] = self.fetchCountries(itemFullPage, itemUrl)
                    item['genres'] = self.fetchGenres(itemFullPage, itemUrl)
                    item['directors'] = self.fetchDirectors(itemFullPage, itemUrl)
                    item['roles'] = self.fetchRoles(itemFullPage, itemUrl)
                    item['rating'] = '0' # no data
                    item['folderItems'] = self.downloadFolder(item['id'], item['type'])

                    items.append(item)
                    # Yeah, I know that keeping a state is not so good for this, but this entire code is a quick hack. :)
                    self.items[item['id']] = item;

        hasMorePages = True if len(fullPage.cssselect('.next-link')) > 0 else False
        pageElems = fullPage.xpath('//div[@class="b-pager"]/ul/li/a[@class="selected"]');
        currentPage = 0
        if len(pageElems):
            # pagination is absent for search results
            pageElem = pageElems[0]
            currentPage = int(pageElem.text_content().strip()) - 1 # zero-based for requests

        return {
            'status': 200,
            'items': items,
            'pagination': {'current': currentPage, 'hasMore': hasMorePages}
        }

    ####################################################################################################
    def requestFolder(self, itemId, itemType, folderId):
        try:
            return {
                'status': 200,
                'folderItems': self.downloadFolder(itemId, itemType, folderId)
            }
        except:
            Log.Exception('Error querying folder')
            return {'status':500, 'folderItems':[]}

    ####################################################################################################
    def downloadFolder(self, itemId, itemType, folderId = 0):
        ajaxUrl = AJAX_REQUEST % (itemType, itemId, itemId, folderId)
        parentElem = HTML.ElementFromURL(ajaxUrl)
        return self.fetchFolder(itemId, itemType, parentElem, folderId)

    ####################################################################################################
    def fetchFolder(self, itemId, itemType, parentElem = None, folderId = '0'):
        folderItems = []
        childItems = parentElem.xpath('./li')
        # for multi-series and single-serie movies file item id is always 'series-s0e0' (though I wish it could be 'series-s0eX')
        multiseries = {}
        seId = ''
        # traverse
        for childItem in childItems:
            anchorsWithId = childItem.xpath('./div/a')
            if len(anchorsWithId):
                # another folder, proceed recursively
                anchorWithId = anchorsWithId[0]
                childFolderId = anchorWithId.attrib['name'].strip()[2 : ]
                childFolderElems = childItem.xpath('./ul')
                childFolderElem = None if len(childFolderElems) == 0 else childFolderElems[0]
                childFolderItems = self.fetchFolder(itemId, itemType, childFolderElem, childFolderId) if childFolderElem != None else []
                folder = {
                    'type' : 'folder',
                    'id' : childFolderId,
                    'title' : anchorWithId.text_content().strip(),
                    'folderItems' : childFolderItems,
                    'downloaded' : childFolderElem != None
                }
                folderItems.append(folder)
            else:
                # otherwise it is not a folder, but file list entry
                try:
                    classList = childItem.attrib['class']
                    # for unknown reason there can be this weird 'li' element, just skip it
                    if classList == 'b-transparent-area':
                        continue
                    videoAttrs = classList.split();
                    seId = videoAttrs[-1]
                    qualityId = videoAttrs[-2]
                    videoLinks = childItem.xpath('./a')
                    # video is available online only if there are both links to view and download
                    if len(videoLinks) == 2:
                        videoLink = videoLinks[0]
                        videoUrl = self.fixVideoUrl(videoLink.attrib['href'])
                        idParts = videoLinks[1].attrib['id'].split('_')
                        fileName = videoLinks[1].attrib['href'].split('/')[-1]
                        fileId = idParts[-1]
                        videoTitleElems = childItem.cssselect('.b-file-new__link-material-filename-series-num')
                        videoTitle = '' if len(videoTitleElems) == 0 else videoTitleElems[0].text_content().strip()
                        if seId == 'series-s0e0':
                            # a multi-series or sigle-serie movie item
                            # group them by quality, then 'reverse' to required format
                            if not qualityId in multiseries:
                                multiseries[qualityId] = []
                            multiseries[qualityId].append({'url' : videoUrl, 'fileName' : fileName, 'fileId' : fileId})

                        else:
                            # lookup if already added with another quality
                            fItemFound = False
                            for fItem in folderItems:
                                if fItem['type'] != 'video':
                                    continue
                                if fItem['seId'] == seId:
                                    fItem['items'].append({'qualityId' : qualityId, 'url' : videoUrl, 'fileName' : fileName, 'fileId' : fileId})
                                    fItemFound = True
                                    break
                            if not fItemFound:
                                video = {
                                    'type' : 'video',
                                    'seId' : seId,
                                    'title' : videoTitle,
                                    'items' : [{'qualityId' : qualityId, 'url' : videoUrl, 'fileName' : fileName, 'fileId' : fileId}]
                                }
                                folderItems.append(video)
                except:
                    # Something went really wrong
                    Log.Exception('Error processing an item entry')
          
        # convert multi-series into a proper format
        # this is no-op for folders without file entries and for serials 
        movieItems = []
        for k,v in multiseries.iteritems():
            for i, item in enumerate(v):
                if i == len(movieItems):
                    movieItems.append({'type' : 'video', 'title' : '', 'items' : []})
                movieItems[i]['items'].append({'qualityId' : k, 'url' : item['url'], 'fileName' : item['fileName'], 'fileId' : item['fileId']})

        return folderItems + movieItems

    ####################################################################################################
    def fixVideoUrl(self, srcUrl):
        return CXZTO_URL + srcUrl.replace('view', 'view_iframe')

    ####################################################################################################
    def fetchItemPoster(self, itemUrl, itemElem):
        try:
            imgElem = itemElem.xpath('./span/img')
            return imgElem[0].attrib['src'];
        except Exception, e:
            Log('Error fetching poster for item %s' % itemUrl)
            Log(e)
            return ''

    ####################################################################################################
    def fetchItemIdFromUrl(self, itemUrl):
        # item url is the following:
        # /films/i1etSlFxkOtzASJ9bPJvZyE-missiya-nevypolnima-plemya-izgojev.html
        # where id is 1etSlFxkOtzASJ9bPJvZyE
        a = itemUrl.find('/i');
        if a == -1:
            return ''
        b = itemUrl.find('-', a)
        if b == -1:
            return ''
        return itemUrl[a + 2 : b]

    ####################################################################################################
    def fetchYear(self, itemFullPage, itemUrl, itemType):
        try:
            yearHref = '/%s/' % itemType
            if itemType in ('tvshow', 'serials', 'cartoonserials'):
                yearHref = yearHref + 'show_start'
            else:
                yearHref = yearHref + 'year'

            xpathQuery = '//a[contains(@href, "%s")]' % yearHref
            yearElem = itemFullPage.xpath(xpathQuery)[0]
            return yearElem.text_content().strip()
        except Exception, e:
            Log('Error fetching year for item %s' % itemUrl)
            Log(e)
            return '1900'

    ####################################################################################################
    def fetchCountries(self, itemFullPage, itemUrl):
        try:
            countries = []
            elemList = itemFullPage.xpath('//a[@class="tag"]')
            for aElem in elemList:
                flagElems = aElem.xpath('./span/span[@class="tag-country-flag"]')
                if len(flagElems):
                    countries.append( {'title' : aElem.text_content().strip()} )
            return countries;
        except Exception, e:
            Log('Error fetching countries for item %s' % itemUrl)
            Log(e)
            return []

    ####################################################################################################
    def fetchGenres(self, itemFullPage, itemUrl):
        try:
            genres = []
            elemList = itemFullPage.xpath('//span[@itemprop="genre"]')
            for aElem in elemList:
                genres.append( {'title' : aElem.text_content().strip().capitalize()} )
            return genres;
        except Exception, e:
            Log('Error fetching genres for item %s' % itemUrl)
            Log(e)
            return []

    ####################################################################################################
    def fetchDirectors(self, itemFullPage, itemUrl):
        try:
            directors = []
            elemList = itemFullPage.xpath('//span[@itemprop="director"]')
            for aElem in elemList:
                directors.append( {'title' : aElem.text_content().strip()} )
            return directors
        except Exception, e:
            Log('Error fetching directors for item %s' % itemUrl)
            Log(e)
            return []

    ####################################################################################################
    def fetchRoles(self, itemFullPage, itemUrl):
        try:
            roles = []
            elemList = itemFullPage.xpath('//span[@itemprop="actor"]')
            for aElem in elemList:
                roles.append( {'role' : aElem.text_content().strip()} )
            return roles;
        except Exception, e:
            Log('Error fetching roles for item %s' % itemUrl)
            Log(e)
            return []

####################################################################################################
def stripTags(inputText):
    inputText = inputText.replace('<br>', '. ')
    tag_re = re.compile(r'(<!--.*?-->|<[^>]*>)')
    return tag_re.sub('', inputText)
