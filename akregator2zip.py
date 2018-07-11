#!/usr/bin/python2
# coding=utf-8
# py2, cause metakit library is pretty much dead and does not support py3...

from __future__ import print_function, division

import sys
sys.dont_write_bytecode = True
import cgi
import codecs
import json
import locale
import os
import shutil
import tempfile
import zipfile
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime

from lxml import etree as et

# git clone https://github.com/jnorthrup/metakit.git
# cd metakit/builds
# ../unix/configure
# make -j4
# cd ../python
# python2 setup.py build -b ../builds
# python2 setup.py install --user
# OR... "emerge metakit" ;-)
import metakit


from a2f_config import ak_archive_path, output_zip, temp_dir


def u(s):
    """Coerces bytestrings to unicode, if needed. Py2+unicode is a little bit annoying..."""
    if not isinstance(s, unicode):
        s = s.decode('utf-8')
    return s

def uesc(s):
    """Returns unicode basic-HTML-escaped string."""
    return u(cgi.escape(s, True))


def read_feeds_opml():
    """Opens Akregator feedlistbackup archive and returns lxml-parsed OPML xml."""
    db = metakit.storage(os.path.join(ak_archive_path, 'feedlistbackup.mk4'), 0)
    vw = db.getas(db.description())
    assert len(vw) == 1, "Expecting one row in feedlistbackup."
    return et.fromstring(vw[0].feedList)


def extract_feed_nodes(opml):
    """Extracts and prepares category: feedlist from OPML document.

    Nested categories are flattened, since FreshRSS does not support them.
    """
    categories = OrderedDict()  # retain original order

    def recursive_scan(outlines, parent_category):
        for outline in outlines:
            if 'xmlUrl' not in outline.attrib:
                # category node
                category = outline.get('text')
                if parent_category:
                    category = parent_category + '/' + category
                categories[category] = []
                recursive_scan(outline.findall('outline'), category)
            else:
                # feed node
                categories[parent_category].append(outline)

    recursive_scan(opml.findall('body/outline'), None)
    return categories


def write_freshrss_opml(feedlist, output_dir):
    """Writes FreshRSS-compatible OPML file."""
    # some stuff that akregator puts in <head>, breaks freshrss importer...
    # lets rewrite it from a scratch, stripping akregator-specific attrs
    root = et.Element('opml', version='2.0')

    head = et.SubElement(root, 'head')
    et.SubElement(head, 'title').text = 'akregator2zip feed export'
    locale.setlocale(locale.LC_TIME, 'C')
    et.SubElement(head, 'dateCreated').text = datetime.today().strftime('%a, %d %b %Y %H:%M:%S')

    leave_attrs = {'text', 'type', 'xmlUrl', 'htmlUrl', 'description', 'version'}
    body = et.SubElement(root, 'body')
    for category, outlines in feedlist.iteritems():
        outline_parent = et.SubElement(body, 'outline', text=category)
        for outline in outlines:
            outline_tag = deepcopy(outline)
            for attr in list(outline_tag.attrib):
                if attr not in leave_attrs:
                    del outline_tag.attrib[attr]
            outline_parent.append(outline_tag)

    with open(os.path.join(output_dir, 'feeds_akregator_export.opml'), 'w') as f:
        f.write(et.tostring(root, encoding='utf-8', xml_declaration=True, pretty_print=True))


def write_feed_json(outline, outnum, output_dir):
    """Writes articles from specified feed (outline) into a JSON file."""
    articles = []
    feed_url = outline.get('xmlUrl')
    html_url = outline.get('htmlUrl')
    feed_title = outline.get('title')
    feed_file = feed_url.replace(':', '_').replace('/', '_') + '.mk4'
    fdb = metakit.storage(os.path.join(ak_archive_path, feed_file), 0)
    vw = fdb.getas(fdb.description())
    article_cnt = len(vw)
    for a in vw:
        if a.hasEnclosure:
            enclosure = ['\n<div class="enclosure">']
            if a.enclosureType.startswith('video/') or a.enclosureType.startswith('audio/'):
                tag = 'video' if a.enclosureType.startswith('video/') else 'audio'
                enclosure.append('<p class="enclosure-content"><')
                enclosure.append(tag)
                enclosure.append(' preload="none" src="')
                enclosure.append(a.enclosureUrl)
                enclosure.append('" controls="controls"></')
                enclosure.append(tag)
                enclosure.append('> <a download="" href="')
                enclosure.append(a.enclosureUrl)
                enclosure.append('">💾</a></p>')
            elif a.enclosureType.startswith('image/'):
                enclosure.append('<p class="enclosure-content"><img src="')
                enclosure.append(a.enclosureUrl)
                enclosure.append('" alt="" /></p>')
            elif a.enclosureType.startswith('application/') or a.enclosureType.startswith('text/'):
                enclosure.append('<p class="enclosure-content"><a download="" href="')
                enclosure.append(a.enclosureUrl)
                enclosure.append('">💾</a></p>')
            enclosure.append('</div>')
            enclosure = ''.join(enclosure)
        else:
            enclosure = ''

        if a.content or a.description or enclosure:
            content = '\n' + (a.content or a.description) + enclosure + '\n'
        else:
            content = ''

        articles.append(OrderedDict([
            ('id', uesc(a.guid)),
            ('categories', [tag for tag in a.tags]),  # akregator does not seem to support tags, although fields exists in database...
            ('title', uesc(a.title)),
            ('author', uesc(a.authorName or a.authorEMail)),
            ('published', a.pubDate),
            ('updated', a.pubDate),
            ('alternate', [OrderedDict([
                ('href', uesc(a.link)),
                ('type', 'text/html'),
            ])]),
            ('content', {
                'content': u(content),
            }),
            ('origin', OrderedDict([
                ('streamId', outnum),
                ('title', uesc(feed_title)),
                ('htmlUrl', uesc(html_url)),
                ('feedUrl', uesc(feed_url)),
            ])),
        ]))

    dump_data = OrderedDict([
        ('id', 'akregator2zip/dump/feed/{}'.format(outnum)),
        ('title', u'List of {} articles'.format(uesc(feed_title))),
        ('author', 'akregator2zip dumper'),
        ('items', articles),
    ])

    dump_file = 'feed_{}_{}.json'.format(datetime.today().strftime('%Y-%m-%d'), outnum)
    with codecs.open(os.path.join(output_dir, dump_file), 'w', 'utf-8') as f:
        json.dump(dump_data, f, ensure_ascii=False, indent=4, separators=(',', ': '))

    return article_cnt


def compress_zipfile(output_dir):
    """Compress files from output_dir into output_zip file."""
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for fname in os.listdir(output_dir):
            fpath = os.path.join(output_dir, fname)
            zipf.write(fpath, fname)


def main():
    opml = read_feeds_opml()
    feedlist = extract_feed_nodes(opml)

    output_dir = tempfile.mkdtemp(prefix='akregator2freshrss_tmp', dir=temp_dir)
    try:
        write_freshrss_opml(feedlist, output_dir)

        i = 0
        total_articles = 0
        for category, outlines in feedlist.iteritems():
            for outline in outlines:
                i += 1
                print(u"Converting #{} '{}'... ".format(i, outline.get('title')), end='')
                sys.stdout.flush()
                article_cnt = write_feed_json(outline, i, output_dir)
                total_articles += article_cnt
                print("{} articles exported".format(article_cnt))

        print("DONE, zipping {} articles...".format(total_articles))
        compress_zipfile(output_dir)
        print("DONE!")
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
