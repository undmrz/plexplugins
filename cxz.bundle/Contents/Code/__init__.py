# -*- coding: utf-8 -*-

####################################################################################################
# 
# This work is licensed under a Creative Commons Attribution 3.0 Unported License.
# See http://creativecommons.org/licenses/by/3.0/deed.en_US for detail.
#
####################################################################################################

import cxzto_api
import urllib2
import urllib
import json
import time
import sys
import base64

sys.setdefaultencoding("utf-8")


ICON                = 'icon-default.png'
ART                 = 'art-default.jpg'
ICON                = 'icon-default.png'
PREFS               = 'icon-prefs.png'
SEARCH              = 'icon-search.png'

PREFIX = '/video/cxz'

cxzapi = cxzto_api.API()

ITEM_URL = cxzto_api.CXZTO_URL + '/item/view'

####################################################################################################
def Start():
    Plugin.AddViewGroup('InfoList', viewMode='InfoList', mediaType='items')
    Plugin.AddViewGroup('List', viewMode='List', mediaType='items')

    ObjectContainer.art = R(ART)
    ObjectContainer.title1 = 'cxz.to'

    DirectoryObject.thumb = R(ICON)
    NextPageObject.thumb = R(ICON)

    PrefsObject.thumb = R(PREFS)
    PrefsObject.art = R(ART)

    InputDirectoryObject.thumb = R(SEARCH)
    InputDirectoryObject.art = R(ART)

    HTTP.CacheTime = CACHE_1HOUR


####################################################################################################
@handler(PREFIX, 'cxz.to', thumb=ICON, art=ART)
def MainMenu():

    oc = ObjectContainer(
        view_group = 'InfoList',
        objects = []
    )

    response = cxzapi.api_request('types')
    if response['status'] == 200:
        for item in response['items']:
            li = DirectoryObject(
                key = Callback(Types, title=item['title'], qp={'type': item['id'], 'genre_id' : item['genre_id']}),
                title = unicode(item['title']),
                summary = unicode(item['title'])
            )
            oc.add(li)
    else:
        return MessageContainer("Error %s" % response['status'], response['message'])
    return oc

####################################################################################################
@route(PREFIX + '/Types', qp=dict)
def Types(title, qp=dict):
    oc = ObjectContainer(
        view_group = 'InfoList',
        objects = [
            InputDirectoryObject(
                key     = Callback(Search, qp=qp),
                title   = unicode('Поиск'),
                prompt  = unicode('Поиск по названию')
            ),
            DirectoryObject(
                key = Callback(Items, title='Последние', qp=merge_dicts(qp, dict({'sort': 'new'}))),
                title = unicode('Последние'),
                summary = unicode('Отсортированные по дате добавления')
            ),
            DirectoryObject(
                key = Callback(Items, title='Популярные', qp=merge_dicts(qp, dict({'sort': 'popularity'}))),
                title = unicode('Популярные'),
                summary = unicode('Отсортированные по количеству просмотров')
            ),
            DirectoryObject(
                key = Callback(Genres, title='Жанры', qp=qp),
                title = unicode('Жанры'),
                summary = unicode('Список жанров')
            ),
        ]
    )
    return oc

####################################################################################################
@route(PREFIX + '/Genres', qp=dict)
def Genres(title, qp=dict):
    response = cxzapi.api_request('genres', params={'type': qp['type'], 'genre_id': qp['genre_id']})
    oc = ObjectContainer(view_group='InfoList')
    if response['status'] == 200:
        for genre in response['items']:
            li = DirectoryObject(
                key = Callback(Items, title=genre['title'], qp={'type':qp['type'], 'genre_id': qp['genre_id'], 'genre': genre['id']}),
                title = genre['title'],
            )
            oc.add(li)
    return oc

####################################################################################################
@route(PREFIX + '/Items', qp=dict)
def Items(title, qp=dict):
    response = cxzapi.api_request('items', qp)
    oc = ObjectContainer(title2=unicode(title), view_group='InfoList')
    if response['status'] == 200:
        video_clips = {}
        @parallelize
        def loadItems():
            for num in xrange(len(response['items'])):
                item = response['items'][num]
                @task
                def loadItemTask(num=num, item=item, video_clips=video_clips):
                    response2 = cxzapi.api_request('items/%s' % item['id'])
                    if response2['status'] == 200:
                        folderItems = response2['item'].get('folderItems', [])
                        folderItems = flattenSinleEntryFolders(folderItems, item)
                        if len(folderItems) == 0:
                            return

                        if len(folderItems) <= 1:
                            item['videos'] = folderItems[0]['items']
                            # create a playable item
                            li = VideoClipObject(
                                url = "%s/freeWatch?data=%s" % (cxzto_api.CXZTO_URL, base64.urlsafe_b64encode(json.dumps(item))),
                                title = item['title'],
                                year = int(item['year']),
                                summary = item['plot'],
                                genres = [x['title'] for x in item['genres']],
                                directors = [x['title'] for x in item['directors']],
                                countries = [x['title'] for x in item['countries']],
                                content_rating = item['rating'],
                                roles = item['roles'],
                                thumb = Resource.ContentsOfURLWithFallback(item['poster'], fallback=R(ICON))
                            )
                            
                        else:
                            # create directory
                            li = DirectoryObject(
                                key = Callback(View, title=item['title'], qp={'id': item['id'], 'folderItems' : folderItems}),
                                title = item['title'],
                                summary = item['plot'],
                                thumb = Resource.ContentsOfURLWithFallback(item['poster'], fallback=R(ICON))
                            )
                        video_clips[num] = li

        for key in sorted(video_clips):
            oc.add(video_clips[key])

        # Add "next page" button
        pagination = response['pagination']
        if pagination['hasMore']:
            qp['page'] = pagination['current'] + 1
            li = NextPageObject(
                key = Callback(Items, title=title, qp=qp),
                title = unicode('Ещё...')
            )
            oc.add(li)
    return oc

####################################################################################################
@route(PREFIX + '/View', qp=dict)
def View(title, qp=dict):
    response = cxzapi.api_request('items/%s' % qp['id'])
    oc = ObjectContainer(title2=unicode(title), view_group='InfoList')
    if response['status'] == 200:
        item = response['item']
        for folderItem in qp['folderItems']:
            if folderItem['type'] == 'video':
                item['videos'] = folderItem['items']
                title2 = item['title'] if len(folderItem['title']) == 0 else folderItem['title']
                # create a playable item
                li = VideoClipObject(
                    url = "%s/freeWatch?data=%s" % (cxzto_api.CXZTO_URL, base64.urlsafe_b64encode(json.dumps(item))),
                    title = title2,
                    year = int(item['year']),
                    summary = str(item['plot']),
                    genres = [x['title'] for x in item['genres']],
                    directors = [x['title'] for x in item['directors']],
                    countries = [x['title'] for x in item['countries']],
                    content_rating = item['rating'],
                    roles = item['roles'],
                    thumb = Resource.ContentsOfURLWithFallback(item['poster'], fallback=R(ICON))
                )
                oc.add(li)
            else:
                downloadFolderIfNeeded(folderItem, item)
                folderItems = flattenSinleEntryFolders(folderItem['folderItems'], item)

                li = DirectoryObject(
                    key = Callback(View, title=folderItem['title'], qp={'id': item['id'], 'folderItems' : folderItems}),
                    title = folderItem['title'],
                    tagline = item['title'],
                    summary = item['plot'],
                    art = Resource.ContentsOfURLWithFallback(item['poster'], fallback=R(ART))
                )
                oc.add(li)       

    return oc

####################################################################################################
@route(PREFIX + '/Search', qp=dict)
def Search(query, qp=dict):
    if qp.get('id'):
        del qp['id']

    return Items('Found', qp=merge_dicts(qp, dict({'query' : query})))

####################################################################################################
def flattenSinleEntryFolders(folderItems, item):
    while len(folderItems) == 1:
        folderItem = folderItems[0]
        if folderItem['type'] == 'folder':
            downloadFolderIfNeeded(folderItem, item)
            folderItems = folderItem['folderItems']
        else:
            break
    return folderItems

####################################################################################################
def downloadFolderIfNeeded(folderItem, item):
    if not folderItem['downloaded']:
        response3 = cxzapi.api_request('folder/%s/%s/%s' % (item['id'], item['type'], folderItem['id']))
        if response3['status'] == 200:
            folderItem['downloaded'] = True
            folderItem['folderItems'] = response3['folderItems']

####################################################################################################
def merge_dicts(*args):
    result = {}
    for d in args:
        result.update(d)
    return result
